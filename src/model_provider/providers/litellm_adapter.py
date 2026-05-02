from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
import json
from typing import Any, Union
import litellm

from src.domain.errors import ModelResponseRepairableError, ModelTokenOverflowError
from src.domain.models import (
    ModelMessage,
    ModelOutputSchema,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    ParsedToolCall
)
from src.domain.capabilities import CapabilityDescription
from src.model_provider.validators.output_parser import (
    SchemaValidationError,
    ToolCallValidationError,
    ModelOutputParser,
)
from src.model_provider.input_normalizer import build_context_budget
from src.observability_hub.exports import ObservabilityHubExports

LiteLLMRawResponse = Union["litellm.ModelResponse", "litellm.CustomStreamWrapper", ModelResponse]

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
    litellm_installed = find_spec("litellm") is not None
    if litellm_installed:
        return LiteLLMRuntimeState(
            litellm_installed=True,
            available=True,
            status="ready",
            litellm_version=version("litellm"),
            metadata={"provider": "litellm"},
        )
    return LiteLLMRuntimeState(
        litellm_installed=False,
        available=False,
        status="degraded",
        reason="litellm_dependency_missing",
        litellm_version=None,
        metadata={"provider": "litellm"},
    )


class LiteLLMAdapter:
    """
    LiteLLM 适配器类 (LiteLLM Adapter)
    封装了 ModelRequest 到 LiteLLM Payload 的转换，以及 LiteLLM 响应到 ModelResponse 的归一化。
    """
    _observability: ObservabilityHubExports | None
    def __init__(
        self,
        observability: ObservabilityHubExports | None = None,
        parser: ModelOutputParser | None = None,
    ) -> None:
        self._observability = observability
        self._parser = parser or ModelOutputParser(observability=observability)

    def _record(self, trace_id: str | None, event: str, payload: Any, level: str = "DEBUG") -> None:
        if self._observability and trace_id:
            self._observability.record(trace_id, {"event": event, "payload": payload}, level)

    def build_litellm_completion_payload(
        self,
        request: ModelRequest,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> dict[str, object]:
        """
        将内部统一的 ModelRequest 对象转换为 LiteLLM 的 completion 函数所需要的参数字典。
        """
        if not isinstance(request.model_name, str):
            raise ValueError("model_request_model_name_required")

        payload: dict[str, object] = {
            "model": request.model_name,
            "messages": tuple(self._to_litellm_message(message) for message in request.messages),
        }
        payload["temperature"] = request.temperature
        payload["top_p"] = request.top_p
        payload["max_tokens"] = request.max_tokens
        if request.tools:
            payload["tools"] = tuple(self._to_litellm_tool(tool) for tool in request.tools)
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
        self,
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
        trace_id = request.metadata.get("trace_id")

        if isinstance(response_raw, ModelResponse):
            return self._return_build_result(
                response_raw,
                self._derive_repair_error_from_response(response_raw),
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
                return self._return_build_result(response, repair_error, capture_repair_error)

            first_choice = response_raw.choices[0]
            message_obj = first_choice.message
            usage_obj = response_raw.usage
            model_name = response_raw.model
            finish_reason = first_choice.finish_reason
            content = self._normalize_message_content(message_obj.content)
            
            # 归一化 usage
            usage = None
            if usage_obj:
                usage = ModelUsage(
                    input_tokens=self._read_token_count(usage_obj, ("prompt_tokens", "input_tokens")),
                    output_tokens=self._read_token_count(usage_obj, ("completion_tokens", "output_tokens")),
                    total_tokens=self._read_token_count(usage_obj, ("total_tokens",)),
                )

            content_effective = "" if content is None else content.strip()

            parsed: object | None = None
            schema_error: SchemaValidationError | None = None

            # 3. 解析 Tool Calls
            tool_calls: tuple[ParsedToolCall, ...] = ()
            tool_call_candidates = message_obj.tool_calls
            if tool_call_candidates:
                try:
                    parsed_tool_calls = self._parser.convert_litellm_tool_calls(
                        tool_call_candidates, 
                        request.tools,
                        trace_id=trace_id,
                    )
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
                    return self._return_build_result(response, exc, capture_repair_error)
            assistant_message = ModelMessage(
                role="assistant",
                content=content,
                tool_calls=tuple(item.invocation for item in tool_calls),
            )

            if output_schema is not None:
                if content_effective:
                    try:
                        parsed = self._parser.parse_message_content(
                            output_schema, 
                            content_effective,
                            trace_id=trace_id,
                        )
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
                return self._return_build_result(response, schema_error, capture_repair_error)

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
                return self._return_build_result(response, None, capture_repair_error)

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
                return self._return_build_result(response, schema_error, capture_repair_error)

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
                return self._return_build_result(response, repair_error, capture_repair_error)

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
            return self._return_build_result(response, None, capture_repair_error)

        raise NotImplementedError(f"Unsupported response type: {type(response_raw)}")

    def _to_litellm_message(self, message: ModelMessage) -> dict[str, object]:
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

    def _to_litellm_tool(self, tool: CapabilityDescription) -> dict[str, object]:
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

    def _read_token_count(self, source: object, field_names: tuple[str, ...]) -> int | None:
        for field_name in field_names:
            value = getattr(source, field_name, None)
            if isinstance(value, int):
                return value
        return None

    def _normalize_message_content(self, content: object) -> str | None:
        if content is None:
            return None
        if isinstance(content, str):
            return content
        raise ValueError("model_message_content_must_be_string")

    def _return_build_result(
        self,
        response: ModelResponse,
        repair_error: ModelResponseRepairableError | None,
        capture_repair_error: bool,
    ) -> ModelResponse | tuple[ModelResponse, ModelResponseRepairableError | None]:
        if capture_repair_error:
            return response, repair_error
        return response

    def _derive_repair_error_from_response(
        self,
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

    def trim_messages(
        self,
        messages: Sequence[Mapping[str, object]],
        *,
        model: str,
        trim_ratio: float = 0.75,
        max_context_tokens: int | None = None,
        reserved_output_tokens: int | None = None,
        trace_id: str | None = None,
    ) -> list[dict[str, object]]:
        """
        实现逻辑块级裁剪与 System 归一化：
        1. 提取并合并所有 system 消息，强制放在首位。
        2. 计算 Token 预算。
        3. 逆序提取对话历史（支持 tool 组原子性），直到填满预算。
        """
        if not messages:
            return []

        # 1. 预算计算
        budget_obj = build_context_budget(
            model,
            max_context_tokens=max_context_tokens,
            reserved_output_tokens=reserved_output_tokens or 4096,
            trim_ratio=trim_ratio
        )
        budget = budget_obj.max_input_tokens

        # 2. System 归一化 (Normalization)
        system_contents = []
        other_messages = []
        for msg in messages:
            if str(msg.get("role") or "") == "system":
                content = msg.get("content")
                if content:
                    system_contents.append(str(content))
            else:
                other_messages.append(msg)

        normalized_system = None
        system_tokens = 0
        if system_contents:
            normalized_system = {
                "role": "system",
                "content": "\n\n".join(system_contents)
            }
            system_tokens = litellm.token_counter(model=model, messages=[normalized_system])

        if system_tokens > budget:
            raise ModelTokenOverflowError(
                f"System messages tokens ({system_tokens}) exceed budget ({budget})",
                budget=budget,
                actual=system_tokens,
            )

        # 3. 逆序提取历史块 (Backward Pass)
        current_tokens = system_tokens
        kept_others = []
        i = len(other_messages) - 1
        
        while i >= 0:
            msg = other_messages[i]
            group_msgs = []
            step = 1
            
            # 处理 Tool 消息原子性
            if str(msg.get("role") or "") == "tool":
                group_msgs = [dict(msg)]
                # 向上找 assistant
                found_assistant = False
                for j in range(i - 1, -1, -1):
                    role = str(other_messages[j].get("role") or "")
                    group_msgs.insert(0, dict(other_messages[j]))
                    step += 1
                    if role == "assistant":
                        found_assistant = True
                        break
                    if role != "tool":
                        # 结构错误，强制跳出
                        break
                
                if not found_assistant:
                    # 孤立的 tool 消息，抛弃这一组
                    i -= step
                    continue
            else:
                group_msgs = [dict(msg)]
                step = 1
            
            group_tokens = litellm.token_counter(model=model, messages=group_msgs)
            if current_tokens + group_tokens <= budget:
                # 保留这组消息（逆序收集，最后反转）
                for g_msg in reversed(group_msgs):
                    kept_others.insert(0, g_msg)
                current_tokens += group_tokens
                i -= step
            else:
                break

        # 4. 组装结果
        res_messages = []
        if normalized_system:
            res_messages.append(normalized_system)
        res_messages.extend(kept_others)

        if self._observability:
            self._observability.record(
                trace_id,
                {
                    "event": "model.completion.trim_messages",
                    "budget": budget,
                    "final_tokens": current_tokens,
                    "message_count": len(res_messages),
                },
                "DEBUG",
            )
        return res_messages
