import inspect
from types import NoneType, UnionType
from typing import Any, Annotated, Callable, Union, get_args, get_origin, Type, TypeVar

from pydantic import Field, create_model, BaseModel
from pydantic.fields import FieldInfo
from src.domain.capabilities import CapabilityDescription

T = TypeVar("T")

class SchemaTranslator:
    """
    Schema 转换器：提供基于 Schema 的自动化推导与数据转换核心能力。
    
    设计意图：
    1. 统一元编程：整合原 tool_parser 的反射逻辑，实现代码到 Model/Schema 的单向流。
    2. 运行时高效：在 CapabilityDescription 中保留 Model 引用，实现极速校验与转换。
    3. 职责收敛：作为全系统唯一的 Schema 处理入口。
    """

    # --- 核心入口接口 ---

    @staticmethod
    def func_to_capability_description(func: Callable, tool_id: str, domain: str = "tool") -> CapabilityDescription:
        """
        核心接口：从函数一键生成完整的领域能力描述对象。
        """
        input_model = SchemaTranslator.func_to_input_model(func)
        output_model = SchemaTranslator.func_to_output_model(func)
        
        return CapabilityDescription(
            capability_id=tool_id,
            domain=domain,
            name=func.__name__,
            description=(func.__doc__ or "").strip() or f"工具 {tool_id}",
            input_schema=SchemaTranslator.model_to_schema(input_model, is_input=True, func=func),
            output_schema=SchemaTranslator.model_to_schema(output_model, is_input=False, func=func),
            input_model=input_model,
            output_model=output_model,
        )

    @staticmethod
    def func_to_input_model(func: Callable) -> Type[BaseModel]:
        """
        1. 提取 Input Model
        解析函数签名（Annotated[Type, Field]），返回聚合了所有参数的 Pydantic Model 类。
        自动跳过 self 和 cls 参数。
        """
        sig = inspect.signature(func)
        fields: dict[str, tuple[Any, Any]] = {}

        for name, param in sig.parameters.items():
            if name in ("self", "cls"):
                continue

            annotation, description = _parse_annotated_contract(
                annotation=param.annotation,
                func=func,
                field_name=name,
                kind_label="parameter",
            )

            has_default = param.default != inspect.Parameter.empty
            default_val = param.default if has_default else ...
            
            fields[name] = (
                annotation,
                Field(default=default_val, description=description),
            )

        return create_model(f"{func.__name__.capitalize()}Params", **fields)

    @staticmethod
    def func_to_output_model(func: Callable) -> Type[BaseModel]:
        """
        2. 提取 Output Model
        解析函数返回值注解，返回一个包装了 'result' 字段的 Pydantic Model 类。
        """
        annotation, description = _parse_annotated_contract(
            annotation=inspect.signature(func).return_annotation,
            func=func,
            field_name="return",
            kind_label="return",
        )

        return create_model(
            f"{func.__name__.capitalize()}Result",
            result=(annotation, Field(default=..., description=description))
        )

    @staticmethod
    def model_to_schema(model: Type[BaseModel], is_input: bool = True, func: Callable | None = None) -> dict[str, Any]:
        """
        3. Model 转 Schema
        将 Pydantic Model 转换为 LLM 友好的 JSON Schema。
        """
        schema = model.model_json_schema()
        schema.pop("title", None)
        
        if "properties" not in schema:
            schema["properties"] = {}

        if is_input and func:
            # 输入 Schema 特有的 LLM 友好化处理
            sig = inspect.signature(func)
            parameter_specs = []
            for name, param in sig.parameters.items():
                if name in ("self", "cls"):
                    continue

                # 显式提取描述以确保注入到最终 Schema
                _, description = _parse_annotated_contract(
                    annotation=param.annotation,
                    func=func,
                    field_name=name,
                    kind_label="parameter",
                )

                parameter_specs.append({
                    "name": name,
                    "description": description,
                    "is_optional": _is_optional_annotation(param.annotation),
                    "has_default": param.default != inspect.Parameter.empty,
                })
            return _normalize_input_schema_for_llm(schema, parameter_specs)
        else:
            # 输出 Schema 处理
            properties = schema.get("properties", {})
            result_schema = properties.get("result")
            if isinstance(result_schema, dict):
                if func:
                    # 显式提取输出描述以确保注入
                    _, description = _parse_annotated_contract(
                        annotation=inspect.signature(func).return_annotation,
                        func=func,
                        field_name="return",
                        kind_label="return",
                    )
                    result_schema["description"] = description
                
                properties["result"] = _strip_top_level_nullability(result_schema)
            
            schema["properties"] = properties
            schema["required"] = ["result"]
            return schema

    @staticmethod
    def validate_payload(model: Type[BaseModel], payload: dict[str, Any]) -> BaseModel:
        """
        4. 验证并转换为 Model 实例
        输入 payload 字典，利用 model 验证数据合法性，并返回实例。
        """
        return model.model_validate(payload)

    @staticmethod
    def serialize_instance(model: Type[BaseModel], instance: Any) -> dict[str, Any]:
        """
        5. 验证并序列化为字典
        对于输出，支持传入原始返回值，自动包装为 {"result": instance} 后进行校验和序列化。
        """
        if not isinstance(instance, dict) or "result" not in instance:
            # 如果不是已经包装好的结构，进行包装
            obj = model.model_validate({"result": instance})
        else:
            obj = model.model_validate(instance)
        return obj.model_dump(mode="json")


# --- 内部辅助函数 (原 tool_parser 迁移) ---

def _parse_annotated_contract(annotation: Any, func: Callable, field_name: str, kind_label: str) -> tuple[Any, str]:
    try:
        # 尝试解包以获取原始函数（处理被装饰器包装的情况）
        raw_func = inspect.unwrap(func)
        source_file = inspect.getsourcefile(raw_func)
        _, line_number = inspect.getsourcelines(raw_func)
    except Exception:
        source_file = "unknown"
        line_number = "unknown"
    
    location = f"File \"{source_file}\", line {line_number}, in {func.__qualname__}"

    if annotation == inspect.Signature.empty:
        raise TypeError(f"{location}: {field_name} must use Annotated[...] and cannot omit type annotation")
    if get_origin(annotation) is not Annotated:
        raise TypeError(f"{location}: {field_name} must use Annotated[...] for {kind_label} schema parsing")
    
    args = get_args(annotation)
    parsed_annotation = args[0]
    description: str | None = None
    for metadata in args[1:]:
        if isinstance(metadata, FieldInfo) and metadata.description:
            description = metadata.description.strip()
            break
        elif isinstance(metadata, str) and metadata.strip():
            description = metadata.strip()
            break
    if not description:
        raise ValueError(f"{location}: {field_name} must provide description via Field(description=...) or Annotated string")
    return parsed_annotation, description

def _normalize_input_schema_for_llm(schema: dict[str, Any], parameter_specs: list[dict[str, Any]]) -> dict[str, Any]:
    properties = schema.get("properties", {})
    required_fields = []
    for spec in parameter_specs:
        name = spec["name"]
        field_schema = properties.get(name)
        if isinstance(field_schema, dict):
            field_schema.pop("default", None)
            field_schema.pop("title", None)
            # 显式注入描述，防止 Pydantic model_json_schema 丢失或将其放入 $defs
            field_schema["description"] = spec["description"]
            if spec["is_optional"]:
                field_schema = _strip_top_level_nullability(field_schema)
            properties[name] = field_schema
        if not spec["is_optional"] and not spec["has_default"]:
            required_fields.append(name)
    schema["required"] = required_fields
    return schema

def _strip_top_level_nullability(field_schema: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(field_schema)
    for union_key in ("anyOf", "oneOf"):
        union_items = normalized.get(union_key)
        if isinstance(union_items, list):
            non_null_items = [item for item in union_items if not (isinstance(item, dict) and item.get("type") == "null")]
            if len(non_null_items) < len(union_items):
                if len(non_null_items) == 1:
                    merged = dict(non_null_items[0])
                    merged.update({k: v for k, v in normalized.items() if k != union_key})
                    normalized = merged
                else:
                    normalized[union_key] = non_null_items
    expected_type = normalized.get("type")
    if isinstance(expected_type, list):
        non_null_types = [t for t in expected_type if t != "null"]
        normalized["type"] = non_null_types[0] if len(non_null_types) == 1 else non_null_types
    return normalized

def _is_optional_annotation(annotation: Any) -> bool:
    """
    判断一个类型注解是否为“可选”类型（即是否包含 None）。
    支持 Union[T, None], T | None 以及被 Annotated 包装后的这些形式。
    """
    # 1. 处理 Annotated[T, ...] 包装的情况
    # get_origin 会返回 Annotated，如果匹配则通过 get_args 提取内部真正的类型 T
    if get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
        
    # 2. 获取基准类型（如 Union 或 UnionType）
    origin = get_origin(annotation)
    
    # 3. 如果不是联合类型，则一定不是可选类型（不考虑直接传 Any 或 None 的极端情况）
    if origin not in (Union, UnionType): 
        return False
        
    # 4. 检查联合类型的参数中是否包含 NoneType (即 None)
    return any(arg is NoneType for arg in get_args(annotation))
