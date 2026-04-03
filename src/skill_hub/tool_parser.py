import inspect
import re
from typing import Any, Callable

def parse_doxygen_to_json_schema(func: Callable) -> dict[str, Any]:
    """
    SH-P0-02: 工具规范解析
    这个函数就像是个“跨国翻译官”。
    大模型（LLM）是不认识 Python 的，它只看得懂官方约定的 JSON Schema 格式。
    这个函数负责强行把咱们中国开发者写的 `@param` 中文注释，加上 Python 的内置种类（像 int / dict），
    一起杂交提纯，最终打包吐出一个闪亮的字典（LLM Tool Spec）。
    """
    docstring = inspect.getdoc(func) or ""

    # 提取函数描述
    # 暴力法：看到 @param 或者 @return 就当做前奏结束，前面的都是总起描述！
    # （这里存在遇到自然句柄中含有此关键词导致被腰斩的漏洞）
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

        # 确定参数类型 (如果有实打实的 Python 类型提示就优先用它，否则看注释有没有写，最后走投无路统统当成 string)
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
