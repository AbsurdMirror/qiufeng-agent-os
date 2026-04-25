from collections.abc import Mapping
from typing import Any
from src.domain.memory import HotMemoryItem


def _dump_hot_memory_item(item: HotMemoryItem) -> dict[str, Any]:
    """将强类型的数据载体序列化为可存储的普通字典"""
    return {
        "trace_id": item.trace_id,
        "role": item.role,
        "content": item.content,
        "metadata": dict(item.metadata),
    }


def _load_hot_memory_item(payload: Mapping[str, Any]) -> HotMemoryItem:
    """从普通字典反序列化出强类型的数据载体，提供容错保护"""
    return HotMemoryItem(
        trace_id=str(payload.get("trace_id", "")),
        role=str(payload.get("role", "")),
        content=str(payload.get("content", "")),
        metadata=dict(payload.get("metadata", {})),
    )
