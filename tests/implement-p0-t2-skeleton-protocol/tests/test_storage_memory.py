import asyncio

import pytest
from src.storage_memory.backends.in_memory import InMemoryHotMemoryStore
from src.domain.context import ContextBlock, ContextLoadRequest, ContextBudget
from src.domain.models import ModelMessage, ToolCallFunction, ToolInvocation

@pytest.fixture
def memory_store():
    return InMemoryHotMemoryStore()

def test_sm_01_lpush_and_lrange(memory_store):
    """测试项 SM-01: 底层原语：lpush 与 lrange"""
    key = "test_list"
    
    # 模拟推入 3 条数据
    asyncio.run(memory_store.lpush(key, {"id": 1, "text": "first"}))
    asyncio.run(memory_store.lpush(key, {"id": 2, "text": "second"}))
    asyncio.run(memory_store.lpush(key, {"id": 3, "text": "third"}))
    
    # 获取所有数据
    items = asyncio.run(memory_store.lrange(key, 0, -1))
    
    assert len(items) == 3
    # lpush 是从左侧推入，最新推入的应该在最前面
    assert items[0]["id"] == 3
    assert items[1]["id"] == 2
    assert items[2]["id"] == 1

def test_sm_02_ltrim_truncation(memory_store):
    """测试项 SM-02: 底层原语：ltrim 截断"""
    key = "test_trim"
    
    for i in range(5):
        asyncio.run(memory_store.lpush(key, {"id": i}))
        
    # 当前列表从左到右: id=4, 3, 2, 1, 0
    # 截断，只保留最新的 3 条 (索引 0, 1, 2)
    asyncio.run(memory_store.ltrim(key, 0, 2))
    
    items = asyncio.run(memory_store.lrange(key, 0, -1))
    assert len(items) == 3
    assert items[0]["id"] == 4
    assert items[1]["id"] == 3
    assert items[2]["id"] == 2

def test_sm_03_append_context_block_with_max_blocks(memory_store):
    """测试项 SM-03: 高层协议：append_context_block"""
    logic_id = "agent_1"
    session_id = "session_abc"
    
    # 连续追加 3 条记录，限制 max_blocks=2
    asyncio.run(
        memory_store.append_context_block(
            logic_id,
            session_id,
            ContextBlock(block_id="b1", kind="user_turn", messages=(ModelMessage(role="user", content="hello 1"),), token_count=10),
            max_blocks=2,
        )
    )
    asyncio.run(
        memory_store.append_context_block(
            logic_id,
            session_id,
            ContextBlock(block_id="b2", kind="user_turn", messages=(ModelMessage(role="user", content="hello 2"),), token_count=10),
            max_blocks=2,
        )
    )
    result = asyncio.run(
        memory_store.append_context_block(
            logic_id,
            session_id,
            ContextBlock(block_id="b3", kind="user_turn", messages=(ModelMessage(role="user", content="hello 3"),), token_count=10),
            max_blocks=2,
        )
    )
    
    assert len(result) == 2
    # 返回的最新记录列表
    assert result[0].block_id == "b2"
    assert result[1].block_id == "b3"


def test_sm_03b_append_context_block_preserves_tool_messages(memory_store):
    logic_id = "agent_tool"
    session_id = "session_tool"
    tool_call = ToolInvocation(
        id="call-1",
        function=ToolCallFunction(name="tool.calc", arguments='{"a":1,"b":2}'),
        type="function"
    )

    result = asyncio.run(
        memory_store.append_context_block(
            logic_id,
            session_id,
            ContextBlock(
                block_id="blk-tool",
                kind="tool_interaction",
                messages=(
                    ModelMessage(
                        role="assistant",
                        content="calling tool",
                        tool_calls=(tool_call,)
                    ),
                    ModelMessage(
                        role="tool",
                        content='{"result":"ok"}',
                        tool_call_id="call-1",
                        name="tool.calc",
                        structured_content={"result": "ok"}
                    )
                ),
                token_count=20
            ),
            max_blocks=5,
        )
    )

    assert len(result) == 1
    block = result[0]
    assert block.kind == "tool_interaction"
    assert len(block.messages) == 2
    
    assistant_msg = block.messages[0]
    tool_msg = block.messages[1]
    
    assert assistant_msg.role == "assistant"
    assert len(assistant_msg.tool_calls) == 1
    
    assert tool_msg.role == "tool"
    assert tool_msg.tool_call_id == "call-1"
    assert tool_msg.name == "tool.calc"
    assert tool_msg.structured_content == {"result": "ok"}

def test_sm_04_runtime_state_persistence(memory_store):
    """测试项 SM-04: 运行时状态持久化与加载"""
    logic_id = "agent_2"
    session_id = "session_xyz"
    
    state = {
        "messages": ["hi"],
        "current_node": "tool_execution"
    }
    
    # 存入状态
    asyncio.run(memory_store.persist_runtime_state(logic_id, session_id, state))
    
    # 读取状态
    loaded_state = asyncio.run(memory_store.load_runtime_state(logic_id, session_id))
    
    assert loaded_state == state
    assert loaded_state is not state  # 应该是深拷贝或新建的字典，不共享内存地址

    # 读取不存在的状态
    empty_state = asyncio.run(memory_store.load_runtime_state("unknown", "unknown"))
    assert empty_state == {}
