import inspect
from typing import Any, Callable, Annotated, get_origin, get_args

from pydantic import create_model, Field

def parse_doxygen_to_json_schema(func: Callable) -> dict[str, Any]:
    """
    SH-P0-02: 工具规范解析
    全面拥抱 Pydantic V2，利用原生函数签名与 Annotated 元数据，
    零冗余生成极其标准、类型安全的 JSON Schema 供大模型调用。
    """
    sig = inspect.signature(func)
    fields = {}

    for name, param in sig.parameters.items():
        # 如果没有注解，默认 Any
        annotation = param.annotation if param.annotation != inspect.Parameter.empty else Any

        # 解析 Annotated 中的 Field description（如果有）
        description = None
        if get_origin(annotation) is Annotated:
            args = get_args(annotation)
            annotation = args[0]  # 提取基础类型
            for arg in args[1:]:
                if isinstance(arg, Field().__class__):
                    description = arg.description
                    break
                elif isinstance(arg, str): # 允许简单的 string 作为 description
                    description = arg
                    break

        # 处理默认值
        default_val = param.default if param.default != inspect.Parameter.empty else ...

        # 组装 Pydantic Field
        if description:
            fields[name] = (annotation, Field(default=default_val, description=description))
        else:
            fields[name] = (annotation, default_val)

    # 动态创建 Pydantic 模型
    model_name = func.__name__.capitalize() + "Params"
    dynamic_model = create_model(model_name, **fields)

    # 获取 JSON schema
    schema = dynamic_model.model_json_schema()

    # 按照 LLM Function Calling 的要求精简清理
    if "title" in schema:
        del schema["title"]

    # Pydantic 在没有参数时可能会缺少 properties 字段
    if "properties" not in schema:
        schema["properties"] = {}

    return schema
