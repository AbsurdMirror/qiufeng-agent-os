import asyncio
import uuid
import time
from typing import Annotated
import pytest
from pydantic import Field

from src.channel_gateway.session.context import SessionContextController
from src.skill_hub.tool_parser import parse_doxygen_to_json_schema
from src.storage_memory.contracts import InMemoryHotMemoryStore, HotMemoryItem

# AT-01: 身份映射幂等性
def test_session_context_mapping():
    controller = SessionContextController()
    
    # 第一次传入 open_id
    open_id = "ou_wx123"
    logical_uuid_1 = controller.get_logical_uuid(open_id)
    
    # 第二次传入同样的 open_id
    logical_uuid_2 = controller.get_logical_uuid(open_id)
    
    # 预期行为：两次输出完全相等，且是合法的 UUID
    assert logical_uuid_1 == logical_uuid_2
    
    # 检查是否合法 UUID
    parsed_uuid = uuid.UUID(logical_uuid_1)
    assert str(parsed_uuid) == logical_uuid_1
    
    # 传入不同 open_id
    logical_uuid_3 = controller.get_logical_uuid("ou_wx456")
    assert logical_uuid_1 != logical_uuid_3

# AT-02: 滑动窗口防重过滤机制
def test_session_context_deduplication():
    # 设防重时间窗口 = 100ms
    controller = SessionContextController(deduplication_window_ms=100)
    
    msg_id = "UUID_1"
    base_time = int(time.time() * 1000)
    
    # 第一次输入，当前时间 baseline
    is_dup_1 = controller.is_duplicate(msg_id, current_timestamp_ms=base_time)
    assert is_dup_1 is False
    
    # 隔 10ms 再次输入
    is_dup_2 = controller.is_duplicate(msg_id, current_timestamp_ms=base_time + 10)
    assert is_dup_2 is True
    
    # 等待 150ms 再次输入
    is_dup_3 = controller.is_duplicate(msg_id, current_timestamp_ms=base_time + 150)
    assert is_dup_3 is False

# AT-03: 工具强格式 Pydantic 映射
def test_tool_parser_pydantic_schema():
    # 设计测试工具函数
    def dummy_tool(
        query: Annotated[str, Field(description="搜索关键字")],
        count: Annotated[int, Field(description="返回条数")] = 10
    ):
        """这是一个测试搜索工具"""
        return f"Searching {query} with {count}"
        
    schema = parse_doxygen_to_json_schema(dummy_tool)
    
    # 验证没有 title
    assert "title" not in schema
    
    # 验证 properties 包含 description
    props = schema.get("properties", {})
    assert "query" in props
    assert props["query"].get("description") == "搜索关键字"
    assert props["query"].get("type") == "string"
    
    assert "count" in props
    assert props["count"].get("description") == "返回条数"
    assert props["count"].get("type") == "integer"
    assert props["count"].get("default") == 10

# AT-04: 热记忆 LIFO 推留截断逻辑
@pytest.mark.asyncio
async def test_hot_memory_lifo_truncation():
    store = InMemoryHotMemoryStore()
    logic_id = "agent_xyz"
    session_id = "session_123"
    
    # 压入 8 轮记录
    for i in range(1, 9):
        item = HotMemoryItem(
            trace_id=f"trace_{i}",
            role="user",
            content=f"Message {i}"
        )
        # 限制 max_rounds=5
        await store.append_hot_memory(logic_id, session_id, item, max_rounds=5)
        
    # 读取历史
    items = await store.read_hot_memory(logic_id, session_id, limit=5)
    
    # 预期只剩下 4, 5, 6, 7, 8
    assert len(items) == 5
    assert items[0].content == "Message 4"
    assert items[-1].content == "Message 8"

# AT-05: 上下文全量序列化存储
@pytest.mark.asyncio
async def test_runtime_state_persistence():
    store = InMemoryHotMemoryStore()
    logic_id = "agent_xyz"
    session_id = "session_123"
    
    # 准备复杂字典
    complex_state = {
        "messages": ["hi", "hello"],
        "metadata": {
            "token": 1500,
            "cost": 0.05
        },
        "is_active": True,
        "score": 99.5
    }
    
    # 存入
    await store.persist_runtime_state(logic_id, session_id, complex_state)
    
    # 取出
    loaded_state = await store.load_runtime_state(logic_id, session_id)
    
    assert loaded_state == complex_state
    
    # 确保是深拷贝或至少独立的 Dict
    complex_state["score"] = 100.0
    assert loaded_state["score"] == 99.5
