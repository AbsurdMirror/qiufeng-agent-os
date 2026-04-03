from typing import Any, Mapping
import copy
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
        在 Agent 启动处理某条消息前，先去数据库（存储层）走一遭。
        就好比医生给病人看病前，提前把病人的“基础病历（历史状态）”和“近期对话（热记忆）”统统拉出来，
        封装进一个大夹子（RuntimeContext）里交给工作流去把玩。
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
        一轮会话处理完毕，准备下班时调用。
        就如同文员下班前，把今天桌面上所有被修改过的数据夹（RuntimeContext Snapshot）
        原封不动地交还给档案室（存储与记忆层）进行落盘保存。
        """
        snapshot = ctx.snapshot()
        state_to_persist = copy.deepcopy(snapshot["state"])

        import logging

        # 调用存储层的持久化接口
        try:
            await self._storage_memory.persist_runtime_state(
                ctx.logic_id,
                ctx.session_id,
                state_to_persist
            )
        except Exception as e:
            logging.error(f"Failed to persist runtime state for session {ctx.session_id}: {e}")
