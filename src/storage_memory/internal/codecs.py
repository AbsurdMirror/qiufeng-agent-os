from collections.abc import Mapping
from typing import Any

from src.domain.context import ContextBlock, ContextBlockKind, SystemPromptPart, SystemPromptPartSource
from src.domain.errors import format_user_facing_error
from src.domain.models import ModelMessage, ToolCallFunction, ToolInvocation


def dump_context_block(block: ContextBlock) -> dict[str, object]:
    """
    将 ContextBlock 对象序列化为可持久化的字典格式。

    Args:
        block: 上下文块对象。

    Returns:
        包含 block_id, kind, messages 和 token_count 的字典。
    """
    return {
        "block_id": block.block_id,
        "kind": block.kind,
        "messages": [dump_model_message(msg) for msg in block.messages],
        "token_count": block.token_count,
    }


def load_context_block(payload: Mapping[str, object]) -> ContextBlock:
    """
    从字典负载中反序列化 ContextBlock 对象。

    Args:
        payload: 包含上下文块数据的字典。

    Returns:
        ContextBlock 对象。

    Raises:
        ValueError: 当数据格式不正确或解析失败时抛出。
    """
    try:
        block_id = str(payload.get("block_id", ""))
        kind = payload.get("kind", "user_turn")
        messages_payload = payload.get("messages", [])
        token_count = int(payload.get("token_count", 0))

        if not isinstance(messages_payload, (list, tuple)):
            raise ValueError("context_block.messages_must_be_sequence")

        messages = tuple(load_model_message(msg) for msg in messages_payload)

        return ContextBlock(
            block_id=block_id,
            kind=kind,  # type: ignore
            messages=messages,
            token_count=token_count,
        )
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            format_user_facing_error(exc, summary="读取上下文块失败")
        ) from exc


def dump_system_prompt_part(part: SystemPromptPart) -> dict[str, object]:
    """
    将 SystemPromptPart 对象序列化为字典。

    Args:
        part: 系统提示词片段对象。

    Returns:
        包含 source 和 content 的字典。
    """
    return {
        "source": part.source,
        "content": part.content,
    }


def load_system_prompt_part(payload: Mapping[str, object]) -> SystemPromptPart:
    """
    从字典中反序列化 SystemPromptPart 对象。

    Args:
        payload: 包含片段数据的字典。

    Returns:
        SystemPromptPart 对象。
    """
    source = payload.get("source", "base_prompt")
    content = str(payload.get("content", ""))
    return SystemPromptPart(
        source=source,  # type: ignore
        content=content,
    )


def dump_model_message(msg: ModelMessage) -> dict[str, object]:
    """
    将 ModelMessage 对象序列化为字典，处理工具调用和元数据。

    Args:
        msg: 模型消息对象。

    Returns:
        包含消息所有属性的字典。
    """
    return {
        "role": msg.role,
        "content": msg.content,
        "tool_calls": [call.to_dict() for call in msg.tool_calls],
        "tool_call_id": msg.tool_call_id,
        "name": msg.name,
        "structured_content": dict(msg.structured_content) if msg.structured_content is not None else None,
        "metadata": dict(msg.metadata),
    }


def load_model_message(payload: Mapping[str, object]) -> ModelMessage:
    """
    从字典中反序列化 ModelMessage 对象。

    Args:
        payload: 包含消息数据的字典。

    Returns:
        ModelMessage 对象。
    """
    role = str(payload.get("role", "user"))
    content = payload.get("content")
    if content is not None:
        content = str(content)

    tool_calls_payload = payload.get("tool_calls", [])
    tool_calls = _load_tool_invocations(tool_calls_payload)

    structured_content = payload.get("structured_content")
    if structured_content is not None and not isinstance(structured_content, Mapping):
        structured_content = None

    return ModelMessage(
        role=role,  # type: ignore
        content=content,
        tool_calls=tool_calls,
        tool_call_id=payload.get("tool_call_id") if isinstance(payload.get("tool_call_id"), str) else None,
        name=payload.get("name") if isinstance(payload.get("name"), str) else None,
        structured_content=dict(structured_content) if structured_content is not None else None,
        metadata=dict(payload.get("metadata", {})),  # type: ignore
    )


def _load_tool_invocations(value: object) -> tuple[ToolInvocation, ...]:
    """
    内部方法：从原始列表加载工具调用（ToolInvocation）列表。
    """
    if not isinstance(value, (list, tuple)):
        return ()
    tool_calls: list[ToolInvocation] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        function_payload = item.get("function")
        if not isinstance(function_payload, Mapping):
            continue
        function_name = function_payload.get("name")
        function_arguments = function_payload.get("arguments")
        if not isinstance(function_name, str) or not isinstance(function_arguments, str):
            continue

        item_id = item.get("id")
        if item_id is not None and not isinstance(item_id, str):
            item_id = str(item_id)

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
