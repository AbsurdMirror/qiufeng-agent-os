import inspect
import re
from typing import Any, Callable

def parse_doxygen_to_json_schema(func: Callable) -> dict[str, Any]:
    """
    SH-P0-02: 工具规范解析
    解析 Python 函数的 Doxygen 风格注释，将其转换为符合 LLM 规范的 Tool Spec (JSON Schema)。
    """
    docstring = inspect.getdoc(func) or ""

    # 提取函数描述
    # 假设描述是 @param 之前的所有文本
    description_match = re.split(r'@param|@return', docstring)
    description = description_match[0].strip() if description_match else ""

    # 提取参数描述
    # 匹配 @param <type> <name> <description> 或 @param <name> <description>
    param_pattern = re.compile(r'@param\s+(?:(\w+)\s+)?(\w+)\s+(.+)')
    params = param_pattern.findall(docstring)

    properties = {}
    required = []

    # 获取函数签名以检查类型注解和默认值
    sig = inspect.signature(func)

    for type_hint, name, param_desc in params:
        param_desc = param_desc.strip()

        # 确定参数类型 (如果有显式类型提示则优先，否则退化为从 doxygen 提取，否则 string)
        param_type = "string"
        if name in sig.parameters:
            annot = sig.parameters[name].annotation
            if annot == int:
                param_type = "integer"
            elif annot == float:
                param_type = "number"
            elif annot == bool:
                param_type = "boolean"
            elif annot == list:
                param_type = "array"
            elif annot == dict:
                param_type = "object"

        if type_hint and type_hint.lower() in ["int", "integer"]:
            param_type = "integer"
        elif type_hint and type_hint.lower() in ["float", "number"]:
            param_type = "number"
        elif type_hint and type_hint.lower() in ["bool", "boolean"]:
            param_type = "boolean"

        properties[name] = {
            "type": param_type,
            "description": param_desc
        }

    for name, param in sig.parameters.items():
        if param.default == inspect.Parameter.empty:
            if name in properties: # Only require it if it is documented
                required.append(name)

    return {
        "type": "object",
        "properties": properties,
        "required": required
    }
