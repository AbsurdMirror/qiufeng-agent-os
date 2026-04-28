from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.capabilities import CapabilityRequest
from src.domain.models import ParsedToolCall
from src.domain.memory import HotMemoryItem
from src.domain.models import ModelMessage

def model_message_to_hot_memory_item(message: ModelMessage, trace_id: str) -> HotMemoryItem:
    from src.domain.memory import HotMemoryItem

    return HotMemoryItem(
        trace_id=trace_id,
        role=message.role,
        content=message.content,
        tool_calls=message.tool_calls,
        tool_call_id=message.tool_call_id,
        name=message.name,
        structured_output=message.structured_content,
        metadata=dict(message.metadata),
    )


def hot_memory_item_to_model_message(item: HotMemoryItem) -> ModelMessage:
    from src.domain.models import ModelMessage

    return ModelMessage(
        role=item.role,
        content=item.content,
        tool_calls=item.tool_calls,
        tool_call_id=item.tool_call_id,
        name=item.name,
        structured_content=item.structured_output,
        metadata=dict(item.metadata),
    )


def model_message_to_debug_dict(message: ModelMessage) -> dict[str, object]:
    return {
        "role": message.role,
        "content": message.content,
        "tool_calls": [call.to_dict() for call in message.tool_calls],
        "tool_call_id": message.tool_call_id,
        "name": message.name,
        "structured_output": dict(message.structured_content) if message.structured_content is not None else None,
        "metadata": dict(message.metadata),
    }


def build_tool_result_message(
    tool_call: ParsedToolCall,
    output: dict[str, object],
) -> ModelMessage:
    from src.domain.models import ModelMessage

    return ModelMessage(
        role="tool",
        content=json.dumps(output, ensure_ascii=False),
        tool_call_id=tool_call.call_id,
        name=tool_call.tool_name,
        structured_content=output,
    )
