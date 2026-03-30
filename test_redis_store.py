import asyncio
from src.storage_memory.bootstrap import initialize
from src.storage_memory.contracts import HotMemoryItem

async def main():
    exports = initialize()

    # Test persist/load state
    state_in = {"key1": "val1", "key2": 42}
    await exports.persist_runtime_state("logic_1", "session_1", state_in)

    state_out = await exports.load_runtime_state("logic_1", "session_1")
    assert state_out["key1"] == "val1"
    assert state_out["key2"] == 42

    # Test append/read hot memory
    item1 = HotMemoryItem(trace_id="trc1", role="user", content="hello")
    await exports.append_hot_memory("logic_1", "session_1", item1, max_rounds=2)

    item2 = HotMemoryItem(trace_id="trc2", role="assistant", content="hi")
    await exports.append_hot_memory("logic_1", "session_1", item2, max_rounds=2)

    item3 = HotMemoryItem(trace_id="trc3", role="user", content="msg3")
    memories = await exports.append_hot_memory("logic_1", "session_1", item3, max_rounds=2)

    # 验证 max_rounds=2
    assert len(memories) == 2
    # 验证最近的排在前面（或者说它保留了最后的两个）

    print("Storage tests passed!")

asyncio.run(main())
