from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
import json

from src.domain.errors import ModelResponseRepairableError
from src.domain.models import (
    ModelMessage,
    ModelOutputSchema,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)
from src.domain.translators.model_interactions import ParsedToolCall
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
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
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
) -> dict[str, object]:
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

    payload: dict[str, object] = {
        "model": request.model_name,
        "messages": tuple(_to_litellm_message(message) for message in request.messages),
    }
    payload["temperature"] = request.temperature
    payload["top_p"] = request.top_p
    payload["max_tokens"] = request.max_tokens
    if request.tools:
        payload["tools"] = tuple(_to_litellm_tool(tool) for tool in request.tools)
    if api_key:
        payload["api_key"] = api_key
    if base_url:
        payload["base_url"] = base_url
    if request.output_schema is not None:
        payload["response_format"] = request.output_schema

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
    output_schema: ModelOutputSchema | None,
    fallback_model_name: str,
    provider_id: str,
    capture_repair_error: bool = False,
) -> ModelResponse | tuple[ModelResponse, ModelResponseRepairableError | None]:
    """
    统一构造 ModelResponse：
    直接根据 response_raw 的类型（dict 或 LiteLLM 对象）提取数据。
    """
    if isinstance(response_raw, ModelResponse):
        return _return_build_result(
            response_raw,
            _derive_repair_error_from_response(response_raw),
            capture_repair_error,
        )

    if isinstance(response_raw, litellm.ModelResponse):
        if not response_raw.choices:
            response = ModelResponse(
                success=False,
                model_name=fallback_model_name,
                content="",
                finish_reason="error",
                provider_id=provider_id,
                repair_reason="model_response_choices_empty",
                raw={"response_raw": str(response_raw)},
            )
            repair_error = SchemaValidationError(
                reason_code="model_response_choices_empty",
                invalid_output="",
                error_text="model_response_choices_empty",
                schema_name=None,
            )
            return _return_build_result(response, repair_error, capture_repair_error)

        first_choice = response_raw.choices[0]
        message_obj = first_choice.message
        usage_obj = response_raw.usage
        model_name = response_raw.model
        finish_reason = first_choice.finish_reason
        content = _normalize_message_content(message_obj.content)
        
        # 归一化 usage
        usage = None
        if usage_obj:
            usage = ModelUsage(
                input_tokens=_read_token_count(usage_obj, ("prompt_tokens", "input_tokens")),
                output_tokens=_read_token_count(usage_obj, ("completion_tokens", "output_tokens")),
                total_tokens=_read_token_count(usage_obj, ("total_tokens",)),
            )

        content_effective = "" if content is None else content.strip()

        parsed: object | None = None
        schema_error: SchemaValidationError | None = None

        # 3. 解析 Tool Calls
        tool_calls: tuple[ParsedToolCall, ...] = ()
        tool_call_candidates = message_obj.tool_calls
        if tool_call_candidates:
            try:
                parsed_tool_calls = convert_litellm_tool_calls(tool_call_candidates, request.tools)
                tool_calls = tuple(parsed_tool_calls)
            except ToolCallValidationError as exc:
                response = ModelResponse(
                    success=False,
                    model_name=model_name,
                    content=content,
                    finish_reason="tool_call_error",
                    provider_id=provider_id,
                    usage=usage,
                    repair_reason=exc.error_text,
                    raw={
                        "response_raw": str(response_raw),
                        "reason": "tool_calls_parse_failed",
                        "tool_error": exc.to_dict(),
                    },
                )
                return _return_build_result(response, exc, capture_repair_error)
        assistant_message = ModelMessage(
            role="assistant",
            content=content,
            tool_calls=tuple(item.invocation for item in tool_calls),
        )

        if output_schema is not None:
            if content_effective:
                try:
                    parsed = parse_message_content(output_schema, content_effective)
                except SchemaValidationError as exc:
                    schema_error = exc
            elif not tool_calls:
                schema_error = SchemaValidationError(
                    reason_code="model_message_content_empty",
                    invalid_output="",
                    error_text="model_message_content_empty",
                    schema_name=None,
                )

        # 5. 构造最终响应
        resolved_finish_reason = str(finish_reason) if finish_reason else "stop"
        
        if tool_calls:
            response = ModelResponse(
                success=True,
                model_name=model_name,
                content=content,
                finish_reason=resolved_finish_reason if resolved_finish_reason != "stop" else "tool_calls",
                provider_id=provider_id,
                usage=usage,
                parsed=parsed,
                tool_calls=tool_calls,
                message=assistant_message,
                repair_reason=schema_error.error_text if schema_error is not None else None,
                raw={"response_raw": str(response_raw)},
            )
            return _return_build_result(response, schema_error, capture_repair_error)

        if parsed is not None:
            response = ModelResponse(
                success=True,
                model_name=model_name,
                content=content,
                finish_reason=resolved_finish_reason,
                provider_id=provider_id,
                usage=usage,
                parsed=parsed,
                tool_calls=tool_calls,
                message=assistant_message,
                raw={"response_raw": str(response_raw)},
            )
            return _return_build_result(response, None, capture_repair_error)

        if output_schema is not None:
            response = ModelResponse(
                success=False,
                model_name=model_name,
                content=content,
                finish_reason="error",
                provider_id=provider_id,
                usage=usage,
                message=assistant_message,
                repair_reason=schema_error.error_text if schema_error is not None else "schema_validation_failed",
                raw={"response_raw": str(response_raw)},
            )
            return _return_build_result(response, schema_error, capture_repair_error)

        if not content_effective:
            repair_error = SchemaValidationError(
                reason_code="model_message_content_empty",
                invalid_output="",
                error_text="model_message_content_empty",
                schema_name=None,
            )
            response = ModelResponse(
                success=False,
                model_name=model_name,
                content=content or "",
                finish_reason="error",
                provider_id=provider_id,
                usage=usage,
                message=assistant_message,
                repair_reason=repair_error.error_text,
                raw={"response_raw": str(response_raw)},
            )
            return _return_build_result(response, repair_error, capture_repair_error)

        response = ModelResponse(
            success=True,
            model_name=model_name,
            content=content,
            finish_reason=resolved_finish_reason,
            provider_id=provider_id,
            usage=usage,
            parsed=parsed,
            tool_calls=tool_calls,
            message=assistant_message,
            raw={"response_raw": str(response_raw)},
        )
        return _return_build_result(response, None, capture_repair_error)

    raise NotImplementedError(f"Unsupported response type: {type(response_raw)}")


def _to_litellm_message(message: ModelMessage) -> dict[str, object]:
    payload: dict[str, object] = {"role": message.role}
    if message.content is not None:
        payload["content"] = message.content
    elif message.structured_content is not None:
        payload["content"] = json.dumps(dict(message.structured_content), ensure_ascii=False)
    else:
        payload["content"] = ""
    if message.tool_calls:
        payload["tool_calls"] = [call.to_dict() for call in message.tool_calls]
    if message.tool_call_id is not None:
        payload["tool_call_id"] = message.tool_call_id
    if message.name is not None:
        payload["name"] = message.name
    return payload


def _to_litellm_tool(tool: CapabilityDescription) -> dict[str, object]:
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


def _read_token_count(source: object, field_names: tuple[str, ...]) -> int | None:
    for field_name in field_names:
        value = getattr(source, field_name, None)
        if isinstance(value, int):
            return value
    return None


def _normalize_message_content(content: object) -> str | None:
    if content is None:
        return None
    if isinstance(content, str):
        return content
    raise ValueError("model_message_content_must_be_string")


def _return_build_result(
    response: ModelResponse,
    repair_error: ModelResponseRepairableError | None,
    capture_repair_error: bool,
) -> ModelResponse | tuple[ModelResponse, ModelResponseRepairableError | None]:
    if capture_repair_error:
        return response, repair_error
    return response


def _derive_repair_error_from_response(
    response: ModelResponse,
) -> ModelResponseRepairableError | None:
    if response.success or response.repair_reason is None:
        return None
    if response.finish_reason == "tool_call_error":
        return ToolCallValidationError(
            response.repair_reason,
            reason_code=response.repair_reason,
            raw_arguments=response.content,
        )
    return SchemaValidationError(
        reason_code=response.repair_reason,
        invalid_output=response.content or "",
        error_text=response.repair_reason,
        schema_name=None,
    )


def _has_dependency(module_name: str) -> bool:
    return find_spec(module_name) is not None


def _read_dependency_version(package_name: str) -> str | None:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return None
