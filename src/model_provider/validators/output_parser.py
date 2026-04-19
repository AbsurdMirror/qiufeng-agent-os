from typing import Any, Mapping, Type, TypeVar
import json
import re

from pydantic import BaseModel, ValidationError

from src.orchestration_engine.contracts import (
    CapabilityDescription,
    CapabilityRequest,
)

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


def parse_message_tool_calls(
    tool_calls: Any,
    tools: tuple[CapabilityDescription, ...],
) -> tuple[CapabilityRequest, ...]:
    """
    解析并校验工具调用，返回可执行的 CapabilityRequest 列表。

    该函数同时完成：
    1. tool_calls 结构解析；
    2. capability_id 白名单校验（必须在 tools 中）；
    3. arguments JSON Schema 校验（基于对应 CapabilityDescription.input_schema）。
    """
    if tool_calls is None:
        return ()
    if not isinstance(tool_calls, list):
        raise ToolCallValidationError("message_tool_calls_must_be_list")

    allowed = {tool.capability_id: tool for tool in tools}
    parsed_requests: list[CapabilityRequest] = []
    for item in tool_calls:
        parsed_requests.append(_parse_and_validate_tool_call_item(item, allowed))
    return tuple(parsed_requests)


def _parse_and_validate_tool_call_item(
    item: Any,
    allowed: dict[str, CapabilityDescription],
) -> CapabilityRequest:
    if not isinstance(item, Mapping):
        raise ToolCallValidationError("tool_call_item_must_be_object")
    function = item.get("function")
    if not isinstance(function, Mapping):
        raise ToolCallValidationError("tool_call_function_must_be_object")

    name = function.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ToolCallValidationError("tool_call_name_required")
    capability_id = name.strip()

    capability = allowed.get(capability_id)
    if capability is None:
        raise ToolCallValidationError(f"tool_not_allowed:{capability_id}")

    payload = _parse_tool_arguments(function.get("arguments"))
    payload_error = _validate_payload_by_schema(payload, capability.input_schema)
    if payload_error is not None:
        raise ToolCallValidationError(f"tool_args_invalid:{capability_id}:{payload_error}")

    metadata: dict[str, Any] = {}
    call_id = item.get("id")
    if isinstance(call_id, str) and call_id.strip():
        metadata["call_id"] = call_id.strip()
    return CapabilityRequest(
        capability_id=capability_id,
        payload=payload,
        metadata=metadata,
    )


def _parse_tool_arguments(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, Mapping):
        return dict(arguments)
    if isinstance(arguments, str):
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
    if arguments is None:
        return {}
    raise ToolCallValidationError("tool_call_arguments_invalid_type")


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
