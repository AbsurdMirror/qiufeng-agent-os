import asyncio
from src.orchestration_engine.context_manager import StateContextManager
from src.orchestration_engine.runtime_context import RuntimeContext

# Mock StorageMemoryExports
class MockStorage:
    async def load_runtime_state(self, logic_id, session_id):
        return {"foo": "bar"}

    async def read_hot_memory(self, logic_id, session_id, limit):
        from src.storage_memory.contracts import HotMemoryItem
        return [HotMemoryItem("user", "hello", 123)]

    async def persist_runtime_state(self, logic_id, session_id, state):
        self.last_state = state

async def main():
    storage = MockStorage()
    manager = StateContextManager(storage)

    ctx = await manager.initialize_context("trace-1", "logic-1", "session-1")
    assert ctx.trace_id == "trace-1"
    assert ctx.get_state("foo") == "bar"
    assert len(ctx.memory["dialogue_history"]) == 1

    manager.update_context(ctx, {"foo": "baz", "new_key": "val"})
    assert ctx.get_state("foo") == "baz"

    await manager.persist_context(ctx)
    assert storage.last_state["foo"] == "baz"
    assert storage.last_state["new_key"] == "val"

    print("StateContextManager tests passed!")

asyncio.run(main())
