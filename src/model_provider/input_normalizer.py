from __future__ import annotations

from collections.abc import Sequence
import litellm
from typing import Mapping

from src.domain.context import (
    ContextBlock,
    ContextBudget,
    SystemPromptPart,
)
from src.domain.models import ModelMessage
from src.domain.errors import ModelTokenOverflowError


def build_context_budget(
    model_name: str,
    *,
    max_context_tokens: int | None = None,
    reserved_output_tokens: int = 4096,
    trim_ratio: float = 0.75,
) -> ContextBudget:
    """
    根据模型名称和配置构建上下文预算。
    """
    def _resolve_context_window() -> int:
        if isinstance(max_context_tokens, int) and max_context_tokens > 0:
            return max_context_tokens
        try:
            # 尝试从 litellm 获取物理窗口
            entry = litellm.model_cost.get(model_name)
            if isinstance(entry, Mapping):
                value = entry.get("max_tokens")
                if isinstance(value, int) and value > 0:
                    return value
            return 128 * 1024  # 默认 128k
        except Exception:
            return 128 * 1024

    max_input = int(_resolve_context_window() * trim_ratio)
    max_input = max(0, max_input - reserved_output_tokens)

    return ContextBudget(
        max_input_tokens=max_input,
        reserved_output_tokens=reserved_output_tokens,
        trim_ratio=trim_ratio,
    )


def merge_system_prompt_parts(
    parts: Sequence[SystemPromptPart],
) -> ModelMessage | None:
    """
    将多个系统提示词片段合并为一个 ModelMessage。
    """
    if not parts:
        return None
    
    contents = [part.content for part in parts if part.content]
    if not contents:
        return None
        
    return ModelMessage(
        role="system",
        content="\n\n".join(contents)
    )


def trim_context_blocks(
    *,
    model_name: str,
    blocks: Sequence[ContextBlock],
    budget: ContextBudget,
    system_message: ModelMessage | None = None,
    current_user_message: ModelMessage | None = None,
) -> tuple[ContextBlock, ...]:
    """
    按块级原子性进行上下文裁剪。
    1. 计算 system 消息和当前用户消息占用的 token。
    2. 逆序检查历史块，直到达到预算上限。
    """
    current_tokens = 0
    
    # 1. 计算必须包含的消息 token
    mandatory_messages = []
    if system_message:
        mandatory_messages.append(system_message)
    if current_user_message:
        mandatory_messages.append(current_user_message)
        
    if mandatory_messages:
        current_tokens = litellm.token_counter(model=model_name, messages=[_to_dict(m) for m in mandatory_messages])
        
    if current_tokens > budget.max_input_tokens:
        raise ModelTokenOverflowError(
            f"Mandatory messages tokens ({current_tokens}) exceed budget ({budget.max_input_tokens})",
            budget=budget.max_input_tokens,
            actual=current_tokens,
        )

    # 2. 逆序收集历史块
    kept_blocks = []
    for block in reversed(blocks):
        # 计算块的 token
        # 优先使用 block 预存的 token_count，如果为 0 则重新计算
        block_tokens = block.token_count
        if block_tokens <= 0:
            block_tokens = litellm.token_counter(model=model_name, messages=[_to_dict(m) for m in block.messages])
            
        if current_tokens + block_tokens <= budget.max_input_tokens:
            kept_blocks.insert(0, block)
            current_tokens += block_tokens
        else:
            # 预算不足，停止收集
            break
            
    return tuple(kept_blocks)


def flatten_context_messages(
    *,
    system_message: ModelMessage | None = None,
    blocks: Sequence[ContextBlock],
    current_user_message: ModelMessage | None = None,
) -> tuple[ModelMessage, ...]:
    """
    将裁剪后的块展开为扁平的消息序列。
    顺序：System -> History Blocks -> Current User Message
    """
    result: list[ModelMessage] = []
    
    if system_message:
        result.append(system_message)
        
    for block in blocks:
        result.extend(block.messages)
        
    if current_user_message:
        result.append(current_user_message)
        
    return tuple(result)


def _to_dict(msg: ModelMessage) -> dict[str, object]:
    """内部辅助：将 ModelMessage 转为 litellm 兼容的字典"""
    payload: dict[str, object] = {"role": msg.role, "content": msg.content or ""}
    if msg.tool_calls:
        payload["tool_calls"] = [call.to_dict() for call in msg.tool_calls]
    if msg.tool_call_id:
        payload["tool_call_id"] = msg.tool_call_id
    if msg.name:
        payload["name"] = msg.name
    return payload
