from collections.abc import Mapping

from src.domain.errors import format_user_facing_error
from src.domain.memory import HotMemoryItem
from src.domain.models import ToolCallFunction, ToolInvocation


def _dump_hot_memory_item(item: HotMemoryItem) -> dict[str, object]:
    """将强类型的数据载体序列化为可存储的普通字典"""
    return {
        "trace_id": item.trace_id,
        "role": item.role,
        "content": item.content,
        "tool_calls": [call.to_dict() for call in item.tool_calls],
        "tool_call_id": item.tool_call_id,
        "name": item.name,
        "structured_output": dict(item.structured_output) if item.structured_output is not None else None,
        "metadata": dict(item.metadata),
    }


def _load_hot_memory_item(payload: Mapping[str, object]) -> HotMemoryItem:
    """从普通字典反序列化出强类型的数据载体，提供容错保护"""
    try:
        content_value = payload.get("content")
        content = content_value if isinstance(content_value, str) or content_value is None else str(content_value)
        tool_calls_payload = payload.get("tool_calls", ())
        tool_calls = _load_tool_invocations(tool_calls_payload)
        metadata_value = payload.get("metadata", {})
        if not isinstance(metadata_value, Mapping):
            raise ValueError("hot_memory.metadata_must_be_mapping")
        structured_output = payload.get("structured_output")
        if structured_output is not None and not isinstance(structured_output, Mapping):
            raise ValueError("hot_memory.structured_output_must_be_mapping")
        return HotMemoryItem(
            trace_id=str(payload.get("trace_id", "")),
            role=str(payload.get("role", "")),
            content=content,
            tool_calls=tool_calls,
            tool_call_id=payload.get("tool_call_id") if isinstance(payload.get("tool_call_id"), str) else None,
            name=payload.get("name") if isinstance(payload.get("name"), str) else None,
            structured_output=dict(structured_output) if isinstance(structured_output, Mapping) else None,
            metadata=dict(metadata_value),
        )
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            format_user_facing_error(exc, summary="读取热记忆消息失败")
        ) from exc


def _load_tool_invocations(value: object) -> tuple[ToolInvocation, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("hot_memory.tool_calls_must_be_sequence")
    tool_calls: list[ToolInvocation] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("hot_memory.tool_call_item_must_be_mapping")
        function_payload = item.get("function")
        if not isinstance(function_payload, Mapping):
            raise ValueError("hot_memory.tool_call_function_must_be_mapping")
        function_name = function_payload.get("name")
        function_arguments = function_payload.get("arguments")
        if not isinstance(function_name, str):
            raise ValueError("hot_memory.tool_call_function_name_must_be_string")
        if not isinstance(function_arguments, str):
            raise ValueError("hot_memory.tool_call_function_arguments_must_be_string")
        item_id = item.get("id")
        if item_id is not None and not isinstance(item_id, str):
            raise ValueError("hot_memory.tool_call_id_must_be_string")
        tool_calls.append(
            ToolInvocation(
                id=item_id,
                function=ToolCallFunction(
                    name=function_name,
                    arguments=function_arguments,
                ),
                type="function",
            )
        )
    return tuple(tool_calls)
