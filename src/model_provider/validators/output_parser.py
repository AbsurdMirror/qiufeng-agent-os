from typing import Any, Mapping, Type, TypeVar
import json
import re

from pydantic import BaseModel, ValidationError

from src.domain.capabilities import CapabilityDescription, CapabilityRequest

from litellm import ChatCompletionMessageToolCall

T = TypeVar("T", bound=BaseModel)


class SchemaValidationError(Exception):
    """content 文本解析或 Pydantic 校验失败。"""


class ToolCallValidationError(Exception):
    """tool_calls 解析或有效性校验失败。"""


def parse_message_content(schema: Type[T], content_str: str) -> T:
    """
    解析并校验模型消息中的 content 文本，返回强类型对象 T。

    注意：
    - 该函数是“解析+Schema 校验”一体化入口。
    - Router 仅在存在 output_schema 时调用该函数；无 schema 时直接使用原始 content。
    """
    if not isinstance(content_str, str):
        raise SchemaValidationError("model_message_content_must_be_string")
    try:
        normalized = re.sub(r'^```(?:json)?\s*\n?', '', content_str, flags=re.IGNORECASE)
        normalized = re.sub(r'\n?```\s*$', '', normalized).strip()
        parsed = json.loads(normalized)
        return schema.model_validate(parsed)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise SchemaValidationError(str(exc)) from exc


def convert_litellm_tool_calls(
    tool_calls: list[ChatCompletionMessageToolCall],
    tools: tuple[CapabilityDescription, ...],
) -> tuple[CapabilityRequest, ...]:
    """
    将 LiteLLM 的工具调用对象列表转换为可执行的 CapabilityRequest 列表。
    仅接受 List[ChatCompletionMessageToolCall] 类型，不进行兼容性检查。
    """
    if not tool_calls:
        return ()

    allowed = {tool.capability_id: tool for tool in tools}
    parsed_requests: list[CapabilityRequest] = []
    for item in tool_calls:
        # 严格按照对象属性访问
        function = item.function
        capability_id = (function.name or "").strip()
        
        capability = allowed.get(capability_id)
        if capability is None:
            raise ToolCallValidationError(
                f"tool_not_allowed:{capability_id}, valid tools: {', '.join(allowed.keys())}"
            )

        # 提取参数并解析
        payload = _parse_tool_arguments(function.arguments)
        
        # 校验参数 Schema
        payload_error = _validate_payload_by_schema(payload, capability.input_schema)
        if payload_error is not None:
            raise ToolCallValidationError(
                f"tool_args_invalid:{capability_id}:{payload_error}"
            )

        metadata: dict[str, Any] = {}
        if item.id:
            metadata["call_id"] = item.id

        parsed_requests.append(CapabilityRequest(
            capability_id=capability_id,
            payload=payload,
            metadata=metadata,
        ))
        
    return tuple(parsed_requests)


def _parse_tool_arguments(arguments: str) -> dict[str, Any]:
    text = arguments.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ToolCallValidationError("tool_call_arguments_must_be_valid_json") from exc
    if not isinstance(parsed, Mapping):
        raise ToolCallValidationError("tool_call_arguments_must_be_object")
    return dict(parsed)


def _validate_payload_by_schema(
    payload: dict[str, Any],
    schema: dict[str, Any],
) -> str | None:
    if not isinstance(schema, dict):
        return None
    required = schema.get("required")
    if isinstance(required, list):
        for key in required:
            if isinstance(key, str) and key not in payload:
                return f"missing_required_field:{key}"
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for key, prop in properties.items():
            if key not in payload:
                continue
            if not isinstance(prop, dict):
                continue
            expected = prop.get("type")
            if expected is None:
                continue
            if not _matches_json_type(payload[key], expected):
                return f"invalid_field_type:{key}:{expected}"
    return None


def _matches_json_type(value: Any, expected_type: Any) -> bool:
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
