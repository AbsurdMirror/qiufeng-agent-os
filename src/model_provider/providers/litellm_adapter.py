from dataclasses import asdict, dataclass, field
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from typing import Any, Mapping

from src.domain.models import ModelMessage, ModelRequest, ModelResponse, ModelUsage, ToolCallFunction, ToolInvocation
from src.model_provider.contracts import LiteLLMRawResponse

import litellm

from src.domain.capabilities import CapabilityDescription
from src.model_provider.validators.output_parser import (
    SchemaValidationError,
    ToolCallValidationError,
    convert_litellm_tool_calls,
    parse_message_content,
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
    if not isinstance(request.model_name, str):
        raise ValueError("model_request_model_name_required")

    payload: dict[str, Any] = {
        "model": request.model_name,
        "messages": tuple(_to_litellm_message(message) for message in request.messages),
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
    if getattr(request, "output_schema", None) is not None:
        payload["response_format"] = request.output_schema
    
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
    response_raw: LiteLLMRawResponse,
    *,
    request: ModelRequest,
    output_schema: Any | None,
    fallback_model_name: str | None,
    provider_id: str | None,
) -> ModelResponse:
    """
    统一构造 ModelResponse：
    直接根据 response_raw 的类型（dict 或 LiteLLM 对象）提取数据。
    """
    if isinstance(response_raw, ModelResponse):
        return response_raw

    elif isinstance(response_raw, litellm.ModelResponse):
        first_choice = response_raw.choices[0]
        message_obj = first_choice.message
        usage_obj = getattr(response_raw, "usage", None)
        model_name = response_raw.model
        finish_reason = first_choice.finish_reason
        content = message_obj.content
        
        # 归一化 usage
        usage = None
        if usage_obj:
            usage = ModelUsage(
                input_tokens=getattr(usage_obj, "prompt_tokens", None) or getattr(usage_obj, "input_tokens", None),
                output_tokens=getattr(usage_obj, "completion_tokens", None) or getattr(usage_obj, "output_tokens", None),
                total_tokens=getattr(usage_obj, "total_tokens", None),
            )

        content_effective = "" if content is None else content.strip()

        parsed = None
        schema_error: str | None = None

        # 3. 解析 Tool Calls
        tool_calls = ()
        tool_invocations: tuple[ToolInvocation, ...] = ()
        if message_obj.tool_calls:
            try:
                tool_calls = convert_litellm_tool_calls(message_obj.tool_calls, request.tools)
                tool_invocations = tuple(
                    ToolInvocation(
                        id=call.id,
                        type="function",
                        function=ToolCallFunction(
                            name=call.function.name,
                            arguments=call.function.arguments,
                        ),
                    )
                    for call in message_obj.tool_calls
                )
            except ToolCallValidationError as exc:
                return ModelResponse(
                    success=False,
                    model_name=str(model_name),
                    content=content,
                    finish_reason="ToolCallValidationError",
                    provider_id=provider_id,
                    usage=usage,
                    repair_reason=str(exc),
                    raw={"response_raw": str(response_raw), "reason": "tool_calls_parse_failed"},
                )
        elif hasattr(message_obj, "function_call") and message_obj.function_call:
            # 兼容旧版 function_call (LiteLLM 会将其转换为对象或保持字典，取决于版本)
            # 但用户要求 parse_message_tool_calls 仅接受 List[ChatCompletionMessageToolCall]
            # 这里如果不符合类型要求，暂时不处理或抛出错误
            pass

        # 4. 构建响应对象
        if output_schema is not None:
            if content_effective:
                try:
                    parsed = parse_message_content(output_schema, content_effective)
                except SchemaValidationError as exc:
                    if not tool_calls:
                        schema_error = str(exc)
            elif not tool_calls:
                schema_error = "model_message_content_empty"

        # 5. 构造最终响应
        resolved_finish_reason = str(finish_reason) if finish_reason else "stop"
        
        if tool_calls:
            return ModelResponse(
                success=True,
                model_name=str(model_name),
                content=content,
                finish_reason=resolved_finish_reason if resolved_finish_reason != "stop" else "tool_calls",
                provider_id=provider_id,
                usage=usage,
                parsed=parsed,
                tool_calls=tool_calls,
                tool_invocations=tool_invocations,
                raw={"response_raw": str(response_raw)},
            )

        if parsed is not None:
            return ModelResponse(
                success=True,
                model_name=str(model_name),
                content=content,
                finish_reason=resolved_finish_reason,
                provider_id=provider_id,
                usage=usage,
                parsed=parsed,
                tool_calls=tool_calls,
                tool_invocations=tool_invocations,
                raw={"response_raw": str(response_raw)},
            )

        if output_schema is not None:
            return ModelResponse(
                success=False,
                model_name=str(model_name),
                content=content,
                finish_reason="error",
                provider_id=provider_id,
                usage=usage,
                repair_reason=schema_error or "schema_validation_failed",
                raw={"response_raw": str(response_raw)},
            )

        if not content_effective:
            return ModelResponse(
                success=False,
                model_name=str(model_name),
                content=content or "",
                finish_reason="error",
                provider_id=provider_id,
                usage=usage,
                repair_reason="model_message_content_empty",
                raw={"response_raw": str(response_raw)},
            )

        return ModelResponse(
            success=True,
            model_name=str(model_name),
            content=content,
            finish_reason=resolved_finish_reason,
            provider_id=provider_id,
            usage=usage,
            parsed=parsed,
            tool_calls=tool_calls,
            tool_invocations=tool_invocations,
            raw={"response_raw": str(response_raw)},
        )
    else:
        raise NotImplementedError(f"Unsupported response type: {type(response_raw)}")


def _to_litellm_message(message: ModelMessage) -> dict[str, object]:
    payload: dict[str, object] = {
        "role": message.role,
        "content": message.content,
    }
    if message.tool_calls:
        payload["tool_calls"] = [asdict(call) for call in message.tool_calls]
    return payload


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


def _has_dependency(module_name: str) -> bool:
    return find_spec(module_name) is not None


def _read_dependency_version(package_name: str) -> str | None:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return None
