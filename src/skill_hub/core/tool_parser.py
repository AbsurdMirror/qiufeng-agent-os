import inspect
from types import NoneType, UnionType
from typing import Any, Annotated, Callable, Union, get_args, get_origin

from pydantic import Field, create_model
from pydantic.fields import FieldInfo


def parse_doxygen_to_json_schema(func: Callable) -> dict[str, Any]:
    """
    解析工具函数的输入参数签名，生成符合 LLM Function Calling 规范的 `input_schema`。

    核心逻辑：
    1. 严格校验：要求每个入参必须显式使用 `Annotated[Type, Field(description="...")]` 声明。
    2. 类型提取：通过 `inspect` 获取函数签名，解析 `Annotated` 中的基础类型与描述信息。
    3. 模型构建：动态创建一个 Pydantic 模型，利用其原生能力生成标准的 JSON Schema。
    4. 针对性优化：为了让 LLM 更易理解，会对生成的 Schema 进行“脱敏”处理：
       - 强制移除 `title` 等冗余字段。
       - 归一化可选参数：移除 `null` 类型分支，仅通过 `required` 数组控制必填性。
       - 隐藏默认值：避免模型在调用时产生混淆。

    Args:
        func: 待解析的 Python 函数对象。

    Returns:
        dict: 经过 LLM 优化后的 JSON Schema 字典。

    Raises:
        TypeError: 当参数未按规范使用 `Annotated` 声明时抛出。
        ValueError: 当参数缺少描述信息（description）时抛出。
    """
    sig = inspect.signature(func)
    fields: dict[str, tuple[Any, Any]] = {}
    parameter_specs: list[dict[str, Any]] = []

    # 遍历函数的所有参数
    for name, param in sig.parameters.items():
        # 解析 Annotated 契约，获取类型和描述
        annotation, description = _parse_annotated_contract(
            annotation=param.annotation,
            owner_name=func.__name__,
            field_name=name,
            kind_label="parameter",
        )

        # 检查是否有默认值
        has_default = param.default != inspect.Parameter.empty
        default_val = param.default if has_default else ...
        
        # 记录 Pydantic 字段定义
        fields[name] = (
            annotation,
            Field(default=default_val, description=description),
        )
        
        # 记录参数规格，用于后续 Schema 归一化
        parameter_specs.append(
            {
                "name": name,
                "is_optional": _is_optional_annotation(annotation),
                "has_default": has_default,
            }
        )

    # 1. 先构建原始的 Pydantic JSON Schema
    schema = _build_schema_from_fields(
        model_name=f"{func.__name__.capitalize()}Params",
        fields=fields,
    )
    
    # 2. 对 Schema 进行 LLM 友好化处理（处理必填项、默认值、可空类型等）
    return _normalize_input_schema_for_llm(schema, parameter_specs)


def parse_function_output_to_json_schema(func: Callable) -> dict[str, Any]:
    """
    解析工具函数的返回值注解，生成与 `CapabilityResult.output` 结构对齐的 `output_schema`。

    设计约定：
    1. 返回值必须声明为 `Annotated[Type, Field(description="...")]`。
    2. 自动将结果包装在名为 `result` 的对象属性中。
    3. `result` 字段始终被标记为 `required`。

    该函数与 `parse_doxygen_to_json_schema` 互为补充，分别负责输入和输出的规范化。

    Args:
        func: 待解析的 Python 函数对象。

    Returns:
        dict: 结构化后的输出 JSON Schema。
    """
    # 解析返回值注解
    annotation, description = _parse_annotated_contract(
        annotation=inspect.signature(func).return_annotation,
        owner_name=func.__name__,
        field_name="return",
        kind_label="return",
    )

    # 构建包含单字段 'result' 的模型 Schema
    schema = _build_schema_from_fields(
        model_name=f"{func.__name__.capitalize()}Result",
        fields={
            "result": (
                annotation,
                Field(default=..., description=description),
            )
        },
    )

    # 针对输出 Schema 的清理
    properties = schema.get("properties", {})
    result_schema = properties.get("result")
    if isinstance(result_schema, dict):
        # 移除返回值顶层的可空性（LLM 应该总是输出有效结果）
        properties["result"] = _strip_top_level_nullability(result_schema)
    
    schema["properties"] = properties
    schema["required"] = ["result"]
    return schema


def _build_schema_from_fields(
    model_name: str,
    fields: dict[str, tuple[Any, Any]],
) -> dict[str, Any]:
    """
    内部助手：基于动态字段定义创建 Pydantic 模型并导出 JSON Schema。
    
    主要完成基础的结构清洗工作。
    """
    # 动态创建 Pydantic 类
    dynamic_model = create_model(model_name, **fields)
    
    # 生成原生 JSON Schema
    schema = dynamic_model.model_json_schema()
    
    # 移除 Pydantic 默认带有的 title，减少 Token 消耗并避免干扰 LLM
    schema.pop("title", None)
    
    # 确保 properties 字段存在，即使是无参函数
    if "properties" not in schema:
        schema["properties"] = {}
        
    return schema


def _parse_annotated_contract(
    annotation: Any,
    owner_name: str,
    field_name: str,
    kind_label: str,
) -> tuple[Any, str]:
    """
    内部助手：严格解析并提取 `Annotated` 中的类型与描述。

    校验逻辑：
    - 必须存在类型注解。
    - 必须使用 `Annotated` 包装。
    - 元数据中必须包含有效的描述字符串（来自 `Field(description=...)` 或直接字符串）。
    """
    # 1. 检查是否存在注解
    if annotation == inspect.Signature.empty:
        raise TypeError(
            f"{owner_name}.{field_name} must use Annotated[...] and cannot omit type annotation"
        )

    # 2. 检查是否为 Annotated 类型
    if get_origin(annotation) is not Annotated:
        raise TypeError(
            f"{owner_name}.{field_name} must use Annotated[...] for {kind_label} schema parsing"
        )

    # 3. 提取基础类型与元数据
    args = get_args(annotation)
    parsed_annotation = args[0]
    description: str | None = None

    # 4. 遍历元数据寻找描述信息
    for metadata in args[1:]:
        # 情况 A: Pydantic Field 对象
        if isinstance(metadata, FieldInfo):
            if metadata.description:
                description = metadata.description.strip()
                break
        # 情况 B: 直接在 Annotated 中写的字符串
        elif isinstance(metadata, str) and metadata.strip():
            description = metadata.strip()
            break

    # 5. 最终校验：描述信息不能为空
    if not description:
        raise ValueError(
            f"{owner_name}.{field_name} must provide description via Field(description=...) or Annotated string"
        )

    return parsed_annotation, description


def _normalize_input_schema_for_llm(
    schema: dict[str, Any],
    parameter_specs: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    内部助手：对生成的参数 Schema 进行 LLM 友好化处理。

    处理策略：
    1. 移除 `default`：默认值由后端处理，不传给 LLM 减少混淆。
    2. 移除类型分支中的 `null`：避免模型纠结于是否该传 null，由必填性控制。
    3. 重新计算 `required` 数组：
       - 只有（非 Optional 且 没有默认值）的参数才标记为必填。
    """
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        schema["properties"] = {}
        properties = schema["properties"]

    required_fields: list[str] = []
    
    # 遍历每个参数的规格进行精细化处理
    for spec in parameter_specs:
        field_name = spec["name"]
        field_schema = properties.get(field_name)
        
        if not isinstance(field_schema, dict):
            # 如果字段在 properties 中不存在，检查是否应为必填
            if not spec["is_optional"] and not spec["has_default"]:
                required_fields.append(field_name)
            continue

        # 清理字段内部的冗余信息
        field_schema.pop("default", None)
        field_schema.pop("title", None)
        
        # 如果是可选类型，尝试移除 schema 中的 null 类型定义
        if spec["is_optional"]:
            field_schema = _strip_top_level_nullability(field_schema)
            
        properties[field_name] = field_schema

        # 核心必填判定逻辑
        if not spec["is_optional"] and not spec["has_default"]:
            required_fields.append(field_name)

    # 更新 Schema 的必填列表
    schema["required"] = required_fields
    return schema


def _strip_top_level_nullability(field_schema: dict[str, Any]) -> dict[str, Any]:
    """
    内部助手：移除 JSON Schema 顶层的可空（null）属性分支。

    例如：
    - `{"anyOf": [{"type": "string"}, {"type": "null"}]}` -> `{"type": "string"}`
    - `{"type": ["string", "null"]}` -> `{"type": "string"}`
    """
    normalized = dict(field_schema)

    # 1. 处理 anyOf / oneOf 结构
    for union_key in ("anyOf", "oneOf"):
        union_items = normalized.get(union_key)
        if not isinstance(union_items, list):
            continue

        # 过滤掉表示 null 的分支
        non_null_items = [item for item in union_items if not _is_null_schema(item)]
        
        # 如果没有包含 null 分支，不做处理
        if len(non_null_items) == len(union_items):
            continue

        # 如果只剩一个有效分支，尝试提升到顶层
        if len(non_null_items) == 1 and isinstance(non_null_items[0], dict):
            merged = dict(non_null_items[0])
            # 保留原有的其他描述性字段（如 description）
            merged.update({key: value for key, value in normalized.items() if key != union_key})
            normalized = merged
        else:
            # 否则只更新过滤后的列表
            normalized[union_key] = non_null_items

    # 2. 处理 type: [..., "null"] 数组形式
    expected_type = normalized.get("type")
    if isinstance(expected_type, list):
        non_null_types = [item for item in expected_type if item != "null"]
        if len(non_null_types) == 1:
            normalized["type"] = non_null_types[0]
        else:
            normalized["type"] = non_null_types

    return normalized


def _is_null_schema(candidate: Any) -> bool:
    """判断一个 Schema 节点是否表示 'null'。"""
    if not isinstance(candidate, dict):
        return False
    candidate_type = candidate.get("type")
    if candidate_type == "null":
        return True
    if isinstance(candidate_type, list):
        return candidate_type == ["null"]
    return False


def _is_optional_annotation(annotation: Any) -> bool:
    """
    判断 Python 类型注解是否显式包含了 None 分支（即可选类型）。
    兼容 Optional[T]、T | None、Union[T, None] 等。
    """
    origin = get_origin(annotation)
    # 处理 Union 或 UnionType (| 操作符)
    if origin not in (Union, UnionType):
        return False
    # 检查参数中是否有 NoneType
    return any(arg is NoneType for arg in get_args(annotation))
