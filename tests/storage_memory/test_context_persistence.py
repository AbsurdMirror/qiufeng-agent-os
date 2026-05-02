import pytest
from src.domain.context import ContextBlock, ContextLoadRequest, ContextBudget
from src.domain.models import ModelMessage
from src.storage_memory.backends.in_memory import InMemoryHotMemoryStore


@pytest.mark.asyncio
async def test_in_memory_block_persistence():
    store = InMemoryHotMemoryStore()
    logic_id = "test-agent"
    session_id = "session-123"
    
    # 1. 创建并追加一个块
    msg = ModelMessage(role="user", content="hello")
    block = ContextBlock(
        block_id="blk-1",
        kind="user_turn",
        messages=(msg,),
        token_count=10
    )
    
    appended_blocks = await store.append_context_block(
        logic_id=logic_id,
        session_id=session_id,
        block=block,
        max_blocks=5
    )
    
    assert len(appended_blocks) == 1
    assert appended_blocks[0].block_id == "blk-1"
    
    # 2. 读取快照
    request = ContextLoadRequest(
        logic_id=logic_id,
        session_id=session_id,
        budget=ContextBudget(100, 50, 0.5),
        include_profile_patch=False,
        include_memory_snippets=False,
        history_block_limit=5
    )
    result = await store.read_context_snapshot(request)
    
    assert len(result.history_blocks) == 1
    assert result.history_blocks[0].messages[0].content == "hello"


@pytest.mark.asyncio
async def test_in_memory_sliding_window():
    store = InMemoryHotMemoryStore()
    logic_id = "test-agent"
    session_id = "session-123"
    
    for i in range(5):
        block = ContextBlock(
            block_id=f"blk-{i}",
            kind="user_turn",
            messages=(ModelMessage(role="user", content=str(i)),),
            token_count=1
        )
        await store.append_context_block(logic_id, session_id, block, max_blocks=3)
        
    request = ContextLoadRequest(
        logic_id=logic_id,
        session_id=session_id,
        budget=ContextBudget(100, 50, 0.5),
        include_profile_patch=False,
        include_memory_snippets=False,
        history_block_limit=10
    )
    result = await store.read_context_snapshot(request)
    
    # 应该只保留最后 3 个
    assert len(result.history_blocks) == 3
    assert result.history_blocks[0].block_id == "blk-2"
    assert result.history_blocks[-1].block_id == "blk-4"
