import pytest
from src.model_provider.providers.litellm_adapter import LiteLLMAdapter


def test_system_normalization():
    adapter = LiteLLMAdapter()
    messages = [
        {"role": "system", "content": "Part 1"},
        {"role": "user", "content": "Hello"},
        {"role": "system", "content": "Part 2"},
    ]
    
    # 我们调用 trim_messages，给一个足够大的预算
    trimmed = adapter.trim_messages(
        messages,
        model="gpt-3.5-turbo",
        max_context_tokens=1000,
        trim_ratio=1.0
    )
    
    assert len(trimmed) == 2
    assert trimmed[0]["role"] == "system"
    assert trimmed[0]["content"] == "Part 1\n\nPart 2"
    assert trimmed[1]["role"] == "user"
    assert trimmed[1]["content"] == "Hello"


def test_block_trimming_with_tool_atomicity():
    adapter = LiteLLMAdapter()
    messages = [
        {"role": "system", "content": "Sys"},
        {"role": "user", "content": "Old msg"},
        {"role": "assistant", "content": "Thinking...", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "t1", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "Result 1"},
        {"role": "user", "content": "New msg"},
    ]
    
    # 模拟预算只能容下 Sys + New msg + Assistant/Tool 组，容不下 Old msg
    # 由于 LiteLLM token_counter 需要真实调用，这里我们通过设置极小的 max_context_tokens 来观察裁剪行为
    
    # 场景 1: 预算充足
    trimmed_all = adapter.trim_messages(messages, model="gpt-3.5-turbo", max_context_tokens=1000)
    assert len(trimmed_all) == 5
    
    # 场景 2: 预算极小，只能保留 System + 最新消息
    # 注意：trim_messages 是逆序保留。
    # 顺序：New msg (User) -> [Tool, Assistant] (Group) -> Old msg (User)
    
    # 我们无法精确控制 token 数，但可以验证原子性：
    # 如果裁剪发生在 Tool 消息处，它必须连带 Assistant 消息一起保留或一起丢弃。
    
    # 验证孤立 Tool 消息及其前面的 User 消息会被丢弃（因为结构不完整，无法保证因果链）
    bad_messages = [
        {"role": "system", "content": "Sys"},
        {"role": "user", "content": "msg 1"},
        {"role": "tool", "tool_call_id": "c1", "content": "orphan tool"},
    ]
    trimmed_bad = adapter.trim_messages(bad_messages, model="gpt-3.5-turbo", max_context_tokens=1000)
    assert len(trimmed_bad) == 1
    assert trimmed_bad[0]["role"] == "system"
