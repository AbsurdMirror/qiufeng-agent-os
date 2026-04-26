from collections.abc import Mapping
from dataclasses import asdict
from typing import Any
from src.domain.memory import HotMemoryItem
from src.domain.models import ToolCallFunction, ToolInvocation


def _dump_hot_memory_item(item: HotMemoryItem) -> dict[str, Any]:
    """将强类型的数据载体序列化为可存储的普通字典"""
    return {
        "trace_id": item.trace_id,
        "role": item.role,
        "content": item.content,
        "tool_calls": [asdict(call) for call in item.tool_calls],
        "metadata": dict(item.metadata),
    }


def _load_hot_memory_item(payload: Mapping[str, Any]) -> HotMemoryItem:
    """从普通字典反序列化出强类型的数据载体，提供容错保护"""
    content = payload.get("content", "")
    tool_calls_payload = payload.get("tool_calls", ())
    tool_calls = tuple(
        ToolInvocation(
            id=item.get("id"),
            function=ToolCallFunction(
                name=item.get("function", {}).get("name"),
                arguments=item.get("function", {}).get("arguments"),
            ),
            type="function",
        )
        for item in tool_calls_payload
    )

    return HotMemoryItem(
        trace_id=str(payload.get("trace_id", "")),
        role=str(payload.get("role", "")),
        content=content,
        tool_calls=tool_calls,
        metadata=dict(payload.get("metadata", {})),
    )
