from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
import json
from typing import Any, Mapping

from src.model_provider.contracts import ModelMessage, ModelRequest, ModelResponse, ModelUsage
from src.orchestration_engine.contracts import CapabilityDescription
from src.model_provider.validators.output_parser import (
    SchemaValidationError,
    ToolCallValidationError,
    parse_message_content,
    parse_message_tool_calls,
)

@dataclass(frozen=True)
class LiteLLMRuntimeState:
    litellm_installed: bool
    available: bool
    status: str
    reason: str | None = None
    litellm_version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "litellm_installed": self.litellm_installed,
            "available": self.available,
            "status": self.status,
            "reason": self.reason,
            "litellm_version": self.litellm_version,
            "metadata": dict(self.metadata),
        }


def probe_litellm_runtime() -> LiteLLMRuntimeState:
    litellm_installed = _has_dependency("litellm")
    litellm_version = _read_dependency_version("litellm")
    if litellm_installed:
        return LiteLLMRuntimeState(
            litellm_installed=True,
            available=True,
            status="ready",
            litellm_version=litellm_version,
            metadata={"provider": "litellm"},
        )
    return LiteLLMRuntimeState(
        litellm_installed=False,
        available=False,
        status="degraded",
        reason="litellm_dependency_missing",
        litellm_version=litellm_version,
        metadata={"provider": "litellm"},
    )


def build_litellm_completion_payload(
    request: ModelRequest,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """
    将内部统一的 ModelRequest 对象转换为 LiteLLM 的 completion 函数所需要的参数字典。
    
    设计意图：
    将我们自己定义的强类型请求结构，平滑地"翻译"成第三方库（LiteLLM）能识别的格式。
    
    初学者提示：
    函数签名中的 `*` 表示后面的参数必须使用关键字方式传入（例如 `api_key="..."`），
    这有助于避免参数顺序传错的问题。
    """
    # 统一在 adapter 层注入工具提示词，避免 provider 侧重复拼接提示词。
    effective_messages = _inject_tool_prompt_messages(request.messages, request.tools)

    if getattr(request, "response_parse", None) and getattr(request.response_parse, "output_schema", None) is not None:
        effective_messages = _inject_output_schema_prompt_messages(effective_messages, request.response_parse.output_schema)

    if not isinstance(request.model_name, str):
        raise ValueError("model_request_model_name_required")

    payload: dict[str, Any] = {
        "model": request.model_name,
        "messages": tuple(
            {"role": message.role, "content": message.content}
            for message in effective_messages
        ),
    }
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.top_p is not None:
        payload["top_p"] = request.top_p
    if request.max_tokens is not None:
        payload["max_tokens"] = request.max_tokens
    if request.tools:
        payload["tools"] = tuple(_to_litellm_tool(tool) for tool in request.tools)
    if api_key:
        payload["api_key"] = api_key
    if base_url:
        payload["base_url"] = base_url
    
    # 缺点与漏洞风险点：这里使用 dict() 只是浅拷贝。
    # 如果 request.metadata 中包含嵌套的可变对象（如列表、字典），在后续修改 payload["metadata"] 时可能会篡改原始请求数据。
    metadata = dict(request.metadata)
    litellm_kwargs = metadata.pop("litellm_kwargs", None)
    if metadata:
        payload["metadata"] = metadata
    if isinstance(litellm_kwargs, Mapping):
        payload.update(dict(litellm_kwargs))
    return payload


def build_model_response(
    response_raw: Any,
    *,
    request: ModelRequest,
    output_schema: Any | None,
    fallback_model_name: str,
    provider_id: str,
) -> ModelResponse:
    """
    统一构造 ModelResponse：
    1. 只抽取一次 choice[0].message；
    2. 使用 output_parser 完成 content/tool_calls 解析；
    3. 产出 success 字段，供 Router 统一做重试判定。
    """
    raw = _to_mapping(response_raw)
    usage_payload = raw.get("usage")
    usage = _normalize_usage(usage_payload if isinstance(usage_payload, Mapping) else {})
    first_choice = _read_first_choice(raw)
    finish_reason = _read_string(first_choice.get("finish_reason"))
    model_name = _read_string(raw.get("model")) or fallback_model_name
    message = _read_choice_message(first_choice)

    # print("response_raw:", response_raw)
    content_value = message.get("content")
    if not isinstance(content_value, str):
        error_raw = dict(raw)
        error_raw["reason"] = "model_message_content_must_be_string"
        # print("content_value:", content_value)
        return ModelResponse(
            success=False,
            model_name=model_name,
            content="",
            finish_reason="error",
            provider_id=provider_id,
            usage=usage,
            repair_reason="model_message_content_must_be_string",
            raw=error_raw,
        )
    content = content_value
    content_effective = content.strip()
    schema_error: str | None = None

    # 先提取 tool_calls 原始结构；若无 tool_calls 但有 function_call，则归一为单条 tool_calls。
    raw_tool_calls = message.get("tool_calls")
    if raw_tool_calls is None:
        function_call = message.get("function_call")
        if isinstance(function_call, Mapping):
            raw_tool_calls = [{"function": function_call}]

    parsed = None
    tool_calls = ()

    try:
        tool_calls = parse_message_tool_calls(raw_tool_calls, request.tools)
    except ToolCallValidationError as exc:
        error_raw = dict(raw)
        error_raw["reason"] = "tool_calls_parse_failed"
        error_raw["message"] = str(exc)
        return ModelResponse(
            success=False,
            model_name=model_name,
            content=content,
            finish_reason="error",
            provider_id=provider_id,
            usage=usage,
            repair_reason=str(exc),
            raw=error_raw,
        )

    # 若声明了 output_schema，则执行“content 解析+schema 校验”一体化流程。
    if output_schema is not None:
        if content_effective:
            try:
                parsed = parse_message_content(output_schema, content_effective)
            except SchemaValidationError as exc:
                if not tool_calls:
                    schema_error = str(exc)
        elif not tool_calls:
            schema_error = "model_message_content_empty"

    if tool_calls:
        success_raw = dict(raw)
        success_raw["tool_calls"] = tuple(
            {
                "capability_id": call.capability_id,
                "payload": dict(call.payload),
                "metadata": dict(call.metadata),
            }
            for call in tool_calls
        )

        resolved_finish_reason = finish_reason
        if not isinstance(resolved_finish_reason, str) or not resolved_finish_reason.strip():
            resolved_finish_reason = "tool_calls"

        return ModelResponse(
            success=True,
            model_name=model_name,
            content=content,
            finish_reason=resolved_finish_reason,
            provider_id=provider_id,
            usage=usage,
            parsed=parsed,
            tool_calls=tool_calls,
            repair_reason=None,
            raw=success_raw,
        )

    elif parsed is not None:
        success_raw = dict(raw)

        resolved_finish_reason = finish_reason
        if not isinstance(resolved_finish_reason, str) or not resolved_finish_reason.strip():
            resolved_finish_reason = "stop"

        return ModelResponse(
            success=True,
            model_name=model_name,
            content=content,
            finish_reason=resolved_finish_reason,
            provider_id=provider_id,
            usage=usage,
            parsed=parsed,
            tool_calls=tool_calls,
            repair_reason=None,
            raw=success_raw,
        )

    elif output_schema is not None:
        error_raw = dict(raw)
        error_raw["reason"] = "schema_validation_failed"
        error_raw["message"] = schema_error or "schema_validation_failed"
        repair_reason = schema_error or "schema_validation_failed"
        return ModelResponse(
            success=False,
            model_name=model_name,
            content=content,
            finish_reason="error",
            provider_id=provider_id,
            usage=usage,
            parsed=parsed,
            tool_calls=tool_calls,
            repair_reason=repair_reason,
            raw=error_raw,
        )

    elif not content_effective:
        error_raw = dict(raw)
        error_raw["reason"] = "model_message_content_empty"
        return ModelResponse(
            success=False,
            model_name=model_name,
            content=content,
            finish_reason="error",
            provider_id=provider_id,
            usage=usage,
            parsed=parsed,
            tool_calls=tool_calls,
            repair_reason="model_message_content_empty",
            raw=error_raw,
        )

    resolved_finish_reason = finish_reason
    if not isinstance(resolved_finish_reason, str) or not resolved_finish_reason.strip():
        resolved_finish_reason = "stop"

    return ModelResponse(
        success=True,
        model_name=model_name,
        content=content,
        finish_reason=resolved_finish_reason,
        provider_id=provider_id,
        usage=usage,
        parsed=parsed,
        tool_calls=tool_calls,
        repair_reason=None,
        raw=dict(raw),
    )


def _normalize_usage(usage_payload: Mapping[str, Any]) -> ModelUsage | None:
    """
    将第三方返回的混乱的 Token 消耗数据，转换为统一的 ModelUsage 结构。
    
    优点：
    容错性强。通过兼容 `prompt_tokens` 和 `input_tokens` 等不同的命名习惯，
    极大地提高了对未知模型提供商的兼容性。
    """
    if not usage_payload:
        return None
    input_tokens = _read_int(
        usage_payload.get("prompt_tokens") or usage_payload.get("input_tokens")
    )
    output_tokens = _read_int(
        usage_payload.get("completion_tokens") or usage_payload.get("output_tokens")
    )
    total_tokens = _read_int(usage_payload.get("total_tokens"))
    return ModelUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _read_first_choice(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    """安全地从原始响应中提取出第一条回复内容（Choice），防止越界或类型错误。"""
    choices = raw.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, Mapping):
            return first_choice
        return _to_mapping(first_choice)
    return {}


def _read_choice_message(choice: Mapping[str, Any]) -> dict[str, Any]:
    message = choice.get("message")
    if isinstance(message, Mapping):
        return dict(message)
    if message is not None:
        return _to_mapping(message)
    return {}


def _to_litellm_tool(tool: CapabilityDescription) -> dict[str, Any]:
    capability_id = tool.capability_id
    description = tool.description
    input_schema = tool.input_schema
    return {
        "type": "function",
        "function": {
            "name": capability_id,
            "description": description,
            "parameters": dict(input_schema),
        },
    }


def _inject_tool_prompt_messages(
    messages: tuple[ModelMessage, ...],
    tools: tuple[CapabilityDescription, ...],
) -> tuple[ModelMessage, ...]:
    if not tools:
        return messages
    tool_lines = [
        "工具调用规则：",
        "1. 仅可调用下列 capability_id；",
        "2. 参数必须严格符合对应 input_schema；",
        "3. 调用工具时输出 tool_calls，不输出多余自然语言。",
        "允许工具列表：",
    ]
    for tool in tools:
        schema_text = json.dumps(tool.input_schema, ensure_ascii=False)
        tool_lines.append(f"- capability_id: {tool.capability_id}")
        if tool.description:
            tool_lines.append(f"  description: {tool.description}")
        tool_lines.append(f"  input_schema: {schema_text}")
    system_prompt = "\n".join(tool_lines)
    return (ModelMessage(role="system", content=system_prompt),) + messages


def _inject_output_schema_prompt_messages(
    messages: tuple[ModelMessage, ...],
    output_schema: Any | None,
) -> tuple[ModelMessage, ...]:
    if output_schema is None:
        return messages
    
    schema_dict = {}
    if hasattr(output_schema, "model_json_schema") and callable(output_schema.model_json_schema):
        schema_dict = output_schema.model_json_schema()
    elif hasattr(output_schema, "schema") and callable(output_schema.schema):
        schema_dict = output_schema.schema()
        
    if not schema_dict:
        return messages

    schema_text = json.dumps(schema_dict, ensure_ascii=False)
    schema_lines = [
        "输出格式规则：",
        "1. 必须返回合法的 JSON 字符串；",
        "2. JSON 结构必须严格符合下列 output_schema；",
        "3. 不要输出任何多余的自然语言解释。",
        "output_schema：",
        schema_text,
    ]
    system_prompt = "\n".join(schema_lines)
    return (ModelMessage(role="system", content=system_prompt),) + messages


def _to_mapping(data: Any) -> dict[str, Any]:
    """
    将对象（尤其是 Pydantic V1 / V2 的模型）统一转换为 Python 字典。
    这是一种经典的防御性编程，避免因为第三方库返回的数据类型奇怪而报错。
    """
    if isinstance(data, Mapping):
        return dict(data)
    # 尝试兼容 Pydantic V2 的 model_dump 方法
    model_dump = getattr(data, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    # 尝试兼容 Pydantic V1 的 dict 方法
    dict_method = getattr(data, "dict", None)
    if callable(dict_method):
        dumped = dict_method()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    return {}


def _read_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _read_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _has_dependency(module_name: str) -> bool:
    return find_spec(module_name) is not None


def _read_dependency_version(package_name: str) -> str | None:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return None
