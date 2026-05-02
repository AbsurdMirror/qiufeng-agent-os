import json

from src.domain.context import ContextBlock
from src.domain.models import ParsedToolCall, ModelMessage


def build_user_context_block(
    *,
    block_id: str,
    user_message: ModelMessage,
    token_count: int,
) -> ContextBlock:
    """构建用户回合上下文块。"""
    return ContextBlock(
        block_id=block_id,
        kind="user_turn",
        messages=(user_message,),
        token_count=token_count,
    )


def build_assistant_answer_block(
    *,
    block_id: str,
    assistant_message: ModelMessage,
    token_count: int,
) -> ContextBlock:
    """构建助手回答上下文块。"""
    return ContextBlock(
        block_id=block_id,
        kind="assistant_answer",
        messages=(assistant_message,),
        token_count=token_count,
    )


def build_tool_interaction_block(
    *,
    block_id: str,
    assistant_message: ModelMessage,
    tool_messages: tuple[ModelMessage, ...],
    token_count: int,
) -> ContextBlock:
    """构建工具交互上下文块（包含助手的工具调用和对应的工具结果）。"""
    return ContextBlock(
        block_id=block_id,
        kind="tool_interaction",
        messages=(assistant_message, *tool_messages),
        token_count=token_count,
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
    return ModelMessage(
        role="tool",
        content=json.dumps(output, ensure_ascii=False),
        tool_call_id=tool_call.call_id,
        name=tool_call.tool_name,
        structured_content=output,
    )
