import asyncio
import pytest
import sqlite3
import json
from pathlib import Path
from src.storage_memory.backends.sqlite_cold import SQLiteColdMemory
from src.domain.context import ContextBlock
from src.domain.models import ModelMessage

@pytest.mark.asyncio
async def test_sqlite_cold_memory_archive_and_query(tmp_path):
    db_path = tmp_path / "test_cold.db"
    cold_mem = SQLiteColdMemory(db_path=db_path)
    
    logic_id = "test_agent"
    session_id = "session_123"
    
    # 构造两个块
    block1 = ContextBlock(
        block_id="blk_1",
        kind="user_turn",
        messages=(ModelMessage(role="user", content="Hello"),),
        token_count=10
    )
    block2 = ContextBlock(
        block_id="blk_2",
        kind="assistant_answer",
        messages=(ModelMessage(role="assistant", content="Hi there!"),),
        token_count=15
    )
    
    # 归档
    await cold_mem.archive_block(logic_id, session_id, block1)
    await cold_mem.archive_block(logic_id, session_id, block2)
    
    # 查询
    history = await cold_mem.query_history(logic_id, session_id)
    
    assert len(history) == 2
    assert history[0]["block_id"] == "blk_1"
    assert history[1]["block_id"] == "blk_2"
    
    # 验证内容序列化
    payload1 = json.loads(history[0]["payload_json"])
    assert payload1["block_id"] == "blk_1"
    assert payload1["messages"][0]["content"] == "Hello"

@pytest.mark.asyncio
async def test_cold_memory_initialization_creates_db(tmp_path):
    db_path = tmp_path / "sub/dir/cold.db"
    cold_mem = SQLiteColdMemory(db_path=db_path)
    assert db_path.exists()
    
    # 验证表是否存在
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='context_archives'")
        assert cursor.fetchone() is not None
