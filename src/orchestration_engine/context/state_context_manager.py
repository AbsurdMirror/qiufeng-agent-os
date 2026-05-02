import copy
import logging
from typing import Mapping

from src.domain.context import ContextLoadRequest, RuntimeMemorySnapshot
from src.model_provider.contracts import ModelProviderClient
from src.orchestration_engine.context.runtime_context import RuntimeContext
from src.storage_memory.exports import StorageMemoryExports


class StateContextManager:
    """
    状态与运行时上下文管理器 (State & Runtime Context Manager)
    """
    def __init__(self, storage_memory: StorageMemoryExports, model_provider: ModelProviderClient):
        self._storage_memory = storage_memory
        self._model_provider = model_provider

    async def initialize_context(
        self,
        trace_id: str,
        logic_id: str,
        session_id: str,
        model_name: str | None = None,
    ) -> RuntimeContext:
        """
        OE-P0-04: 记忆读取 (Memory Loading)
        """
        # 1. 获取模型预算握手 (MP-P0-02)
        budget = self._model_provider.get_context_budget(model_name or "default")

        # 2. 构造加载请求 (SM-P0-04)
        load_request = ContextLoadRequest(
            logic_id=logic_id,
            session_id=session_id,
            budget=budget,
            include_profile_patch=True,
            include_memory_snippets=True,
            history_block_limit=10  # 默认读取最近 10 个逻辑块
        )

        # 3. 加载持久化状态
        persisted_state = await self._storage_memory.load_runtime_state(logic_id, session_id)

        # 4. 加载上下文快照 (包含逻辑块与系统片段)
        load_result = await self._storage_memory.read_context_snapshot(load_request)

        # 5. 组装 Memory 快照
        memory_snapshot = RuntimeMemorySnapshot(
            system_parts=load_result.system_parts,
            history_blocks=load_result.history_blocks
        )

        # 6. 初始化 RuntimeContext
        ctx = RuntimeContext(
            trace_id=trace_id,
            logic_id=logic_id,
            session_id=session_id,
            memory=memory_snapshot,
            state=persisted_state
        )
        return ctx

    def update_context(self, ctx: RuntimeContext, updates: Mapping[str, object]) -> None:
        """
        OE-P0-05: 上下文维护 (Context Maintenance)
        """
        for key, value in updates.items():
            ctx.set_state(key, value)

    async def persist_context(self, ctx: RuntimeContext) -> None:
        """
        OE-P0-06: 状态持久化 (State Persistence)
        """
        snapshot = ctx.snapshot()
        state_to_persist = copy.deepcopy(snapshot["state"])

        try:
            await self._storage_memory.persist_runtime_state(
                ctx.logic_id,
                ctx.session_id,
                state_to_persist  # type: ignore
            )
        except Exception as e:
            logging.error(f"Failed to persist runtime state for session {ctx.session_id}: {e}")
