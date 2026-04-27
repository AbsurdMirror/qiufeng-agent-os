from collections.abc import Mapping, Sequence
import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from src.domain.capabilities import CapabilityDescription, CapabilityRequest
from src.domain.errors import ModelResponseRepairableError
from src.domain.models import ToolCallFunction, ToolInvocation
from src.domain.translators.model_interactions import ParsedToolCall

from litellm import ChatCompletionMessageToolCall

T = TypeVar("T", bound=BaseModel)


class SchemaValidationError(ModelResponseRepairableError):
    """content 文本解析或 Pydantic 校验失败。"""

    def __init__(
        self,
        *,
        reason_code: str,
        invalid_output: str,
        error_text: str,
        schema_name: str | None,
    ) -> None:
        super().__init__(
            reason_code=reason_code,
            target_label="输出",
            invalid_output=invalid_output,
            error_text=error_text,
        )
        self.schema_name = schema_name

    def to_dict(self) -> dict[str, str]:
        result = super().to_dict()
        result["schema_name"] = self.schema_name or ""
        return result


class ToolCallValidationError(ModelResponseRepairableError):
    """tool_calls 解析或有效性校验失败。"""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        tool_name: str | None = None,
        tool_index: int | None = None,
        raw_arguments: str | None = None,
    ) -> None:
        super().__init__(
            reason_code=reason_code,
            target_label="工具调用",
            invalid_output=raw_arguments or "",
            error_text=message,
        )
        self.tool_name = tool_name
        self.tool_index = tool_index
        self.raw_arguments = raw_arguments

    def to_dict(self) -> dict[str, object]:
        result = super().to_dict()
        result.update(
            {
                "tool_name": self.tool_name,
                "tool_index": self.tool_index,
                "raw_arguments": self.raw_arguments,
            }
        )
        return result


def parse_message_content(
    schema: type[T] | Mapping[str, object],
    content_str: str,
) -> T | object:
    """
    解析并校验模型消息中的 content 文本，返回强类型对象 T。

    注意：
    - 该函数是“解析+Schema 校验”一体化入口。
    - Router 仅在存在 output_schema 时调用该函数；无 schema 时直接使用原始 content。
    """
    try:
        normalized = re.sub(r'^```(?:json)?\s*\n?', '', content_str, flags=re.IGNORECASE)
        normalized = re.sub(r'\n?```\s*$', '', normalized).strip()
        parsed = json.loads(normalized)
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            return schema.model_validate(parsed)
        return parsed
    except (json.JSONDecodeError, ValidationError) as exc:
        raise SchemaValidationError(
            reason_code="schema_validation_failed",
            invalid_output=content_str,
            error_text=str(exc),
            schema_name=_schema_name(schema),
        ) from exc


def convert_litellm_tool_calls(
    tool_calls: Sequence[ChatCompletionMessageToolCall | Mapping[str, object]],
    tools: tuple[CapabilityDescription, ...],
) -> tuple[ParsedToolCall, ...]:
    """
    将 LiteLLM 的工具调用对象列表转换为可执行的 CapabilityRequest 列表。
    仅接受 List[ChatCompletionMessageToolCall] 类型，不进行兼容性检查。
    """
    if not tool_calls:
        return ()

    allowed = {tool.capability_id: tool for tool in tools}
    parsed_requests: list[ParsedToolCall] = []
    for index, item in enumerate(tool_calls):
        invocation = _coerce_tool_invocation(item, tool_index=index)
        capability_id = invocation.function.name.strip()
        capability = allowed.get(capability_id)
        if capability is None:
            raise ToolCallValidationError(
                f"tool_not_allowed:{capability_id}, valid tools: {', '.join(allowed.keys())}",
                reason_code="tool_not_allowed",
                tool_name=capability_id,
                tool_index=index,
                raw_arguments=invocation.function.arguments,
            )

        payload = _parse_tool_arguments(
            invocation.function.arguments,
            tool_name=capability_id,
            tool_index=index,
        )
        
        payload_error = _validate_payload_by_schema(payload, capability.input_schema)
        if payload_error is not None:
            raise ToolCallValidationError(
                f"tool_args_invalid:{capability_id}:{payload_error}",
                reason_code="tool_args_invalid",
                tool_name=capability_id,
                tool_index=index,
                raw_arguments=invocation.function.arguments,
            )

        metadata: dict[str, object] = {}
        if invocation.id:
            metadata["call_id"] = invocation.id

        parsed_requests.append(
            ParsedToolCall(
                invocation=invocation,
                request=CapabilityRequest(
                    capability_id=capability_id,
                    payload=payload,
                    metadata=metadata,
                ),
            )
        )
        
    return tuple(parsed_requests)


def _coerce_tool_invocation(
    item: ChatCompletionMessageToolCall | Mapping[str, object],
    *,
    tool_index: int,
) -> ToolInvocation:
    if isinstance(item, ChatCompletionMessageToolCall):
        function_name = getattr(item.function, "name", None)
        function_arguments = getattr(item.function, "arguments", None)
        if not isinstance(function_name, str) or not function_name.strip():
            raise ToolCallValidationError(
                "tool_call_name_missing",
                reason_code="tool_call_name_missing",
                tool_index=tool_index,
            )
        if not isinstance(function_arguments, str):
            raise ToolCallValidationError(
                "tool_call_arguments_must_be_string",
                reason_code="tool_call_arguments_must_be_string",
                tool_name=function_name,
                tool_index=tool_index,
            )
        return ToolInvocation(
            id=getattr(item, "id", None),
            function=ToolCallFunction(
                name=function_name.strip(),
                arguments=function_arguments,
            ),
            type="function",
        )

    function_payload = item.get("function")
    if not isinstance(function_payload, Mapping):
        raise ToolCallValidationError(
            "tool_call_function_payload_invalid",
            reason_code="tool_call_function_payload_invalid",
            tool_index=tool_index,
        )
    function_name = function_payload.get("name")
    function_arguments = function_payload.get("arguments")
    if not isinstance(function_name, str) or not function_name.strip():
        raise ToolCallValidationError(
            "tool_call_name_missing",
            reason_code="tool_call_name_missing",
            tool_index=tool_index,
        )
    if not isinstance(function_arguments, str):
        raise ToolCallValidationError(
            "tool_call_arguments_must_be_string",
            reason_code="tool_call_arguments_must_be_string",
            tool_name=function_name,
            tool_index=tool_index,
        )
    call_id = item.get("id")
    call_type = item.get("type", "function")
    if call_type != "function":
        raise ToolCallValidationError(
            "tool_call_type_unsupported",
            reason_code="tool_call_type_unsupported",
            tool_name=function_name,
            tool_index=tool_index,
            raw_arguments=function_arguments,
        )
    if call_id is not None and not isinstance(call_id, str):
        raise ToolCallValidationError(
            "tool_call_id_must_be_string",
            reason_code="tool_call_id_must_be_string",
            tool_name=function_name,
            tool_index=tool_index,
            raw_arguments=function_arguments,
        )
    return ToolInvocation(
        id=call_id,
        function=ToolCallFunction(
            name=function_name.strip(),
            arguments=function_arguments,
        ),
        type="function",
    )


def _parse_tool_arguments(
    arguments: str,
    *,
    tool_name: str,
    tool_index: int,
) -> dict[str, object]:
    text = arguments.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ToolCallValidationError(
            "tool_call_arguments_must_be_valid_json",
            reason_code="tool_call_arguments_must_be_valid_json",
            tool_name=tool_name,
            tool_index=tool_index,
            raw_arguments=arguments,
        ) from exc
    if not isinstance(parsed, Mapping):
        raise ToolCallValidationError(
            "tool_call_arguments_must_be_object",
            reason_code="tool_call_arguments_must_be_object",
            tool_name=tool_name,
            tool_index=tool_index,
            raw_arguments=arguments,
        )
    return dict(parsed)


def _validate_payload_by_schema(
    payload: dict[str, object],
    schema: Mapping[str, object],
) -> str | None:
    required = schema.get("required")
    if isinstance(required, list):
        for key in required:
            if isinstance(key, str) and key not in payload:
                return f"missing_required_field:{key}"
    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        for key, prop in properties.items():
            if key not in payload:
                continue
            if not isinstance(key, str) or not isinstance(prop, Mapping):
                continue
            expected = prop.get("type")
            if expected is None:
                continue
            if not _matches_json_type(payload[key], expected):
                return f"invalid_field_type:{key}:{expected}"
    return None


def _matches_json_type(value: object, expected_type: object) -> bool:
    if isinstance(expected_type, list):
        return any(_matches_json_type(value, item) for item in expected_type)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "null":
        return value is None
    return True


def _schema_name(schema: type[T] | Mapping[str, object]) -> str | None:
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return schema.__name__
    return None
