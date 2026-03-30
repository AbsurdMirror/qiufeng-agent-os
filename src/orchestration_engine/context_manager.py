from typing import Any, Mapping
from src.orchestration_engine.runtime_context import RuntimeContext
from src.storage_memory.exports import StorageMemoryExports

class StateContextManager:
    """
    状态与运行时上下文管理器 (State & Runtime Context Manager)
    实现 T4 阶段的 OE-P0-04, OE-P0-05, OE-P0-06 规格
    """
    def __init__(self, storage_memory: StorageMemoryExports):
        self._storage_memory = storage_memory

    async def initialize_context(self, trace_id: str, logic_id: str, session_id: str) -> RuntimeContext:
        """
        OE-P0-04: 记忆读取 (Memory Loading)
        在 Agent 启动时，同步从“存储与记忆层”拉取历史状态及记忆。
        """
        # 加载持久化状态
        persisted_state = await self._storage_memory.load_runtime_state(logic_id, session_id)

        # 加载热记忆 (转换结构为对话历史列表)
        hot_memory_items = await self._storage_memory.read_hot_memory(logic_id, session_id, limit=10)

        # 将 Memory 组装
        memory_dict = {
            "dialogue_history": [
                {"role": item.role, "content": item.content}
                for item in hot_memory_items
            ]
        }

        # 初始化 RuntimeContext
        ctx = RuntimeContext(
            trace_id=trace_id,
            logic_id=logic_id,
            session_id=session_id,
            memory=memory_dict,
            state=persisted_state
        )
        return ctx

    def update_context(self, ctx: RuntimeContext, updates: Mapping[str, Any]) -> None:
        """
        OE-P0-05: 上下文维护 (Context Maintenance)
        实现运行时 RuntimeContext 的动态更新与同步。
        """
        for key, value in updates.items():
            ctx.set_state(key, value)

    async def persist_context(self, ctx: RuntimeContext) -> None:
        """
        OE-P0-06: 状态持久化 (State Persistence)
        实现执行上下文向存储与记忆层的异步持久化。
        """
        snapshot = ctx.snapshot()
        state_to_persist = snapshot["state"]

        # 调用存储层的持久化接口
        await self._storage_memory.persist_runtime_state(
            ctx.logic_id,
            ctx.session_id,
            state_to_persist
        )
