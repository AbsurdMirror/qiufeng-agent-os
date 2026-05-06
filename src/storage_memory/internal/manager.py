from collections.abc import Mapping
from typing import Any

from src.domain.context import (
    ContextBlock,
    ContextLoadRequest,
    ContextLoadResult,
    JSONValue,
    SystemPromptPart,
)
from src.observability_hub.exports import ObservabilityHubExports
from ..contracts.protocols import (
    ColdMemoryProtocol,
    HotMemoryCarrier,
    HotMemoryProtocol,
    ProfileProtocol,
    WarmMemoryProtocol,
)


class StorageMemoryManager:
    """
    存储与记忆统一调度管理类 (Manager)。
    
    内部封装了热、冷、温、用户特征等多个记忆存储模块，
    提供统一的接口对外提供各记忆存储模块的调度与管理功能。
    
    设计意图：
    1. 封装冷热同步、可观测性记录等跨模块编排逻辑。
    2. 屏蔽底层具体后端的差异，提供强类型的业务接口。
    3. 支持各存储层级的动态插件化替换。
    """

    def __init__(
        self,
        *,
        hot: HotMemoryProtocol,
        cold: ColdMemoryProtocol | None = None,
        warm: WarmMemoryProtocol | None = None,
        profile: ProfileProtocol | None = None,
        observability: ObservabilityHubExports | None = None,
    ) -> None:
        self._hot = hot
        self._cold = cold
        self._warm = warm
        self._profile = profile
        self._observability = observability

    @property
    def protocol(self) -> HotMemoryProtocol:
        """获取热记忆存取协议接口"""
        return self._hot

    @property
    def cold_memory(self) -> ColdMemoryProtocol | None:
        return self._cold

    @property
    def warm_memory(self) -> WarmMemoryProtocol | None:
        return self._warm

    @property
    def profile(self) -> ProfileProtocol | None:
        return self._profile

    async def append_context_block(
        self,
        logic_id: str,
        session_id: str,
        block: ContextBlock,
    ) -> tuple[ContextBlock, ...]:
        """
        追加对话块：同步写入热记忆并自动归档至冷记忆。
        """
        if self._observability:
            self._observability.record(
                "system",
                {
                    "event": "storage.context_block.append",
                    "logic_id": logic_id,
                    "session_id": session_id,
                    "block_id": block.block_id,
                    "kind": block.kind,
                    "token_count": block.token_count,
                },
                "DEBUG",
            )

        # 1. 追加到热记忆 (使用初始化时配置的裁剪策略)
        history = await self._hot.append_context_block(
            logic_id=logic_id,
            session_id=session_id,
            block=block,
        )

        # 2. 同步归档到冷记忆 (全量记录)
        if self._cold:
            await self._cold.archive_block(logic_id, session_id, block)

        return history

    async def archive_context_block(
        self,
        logic_id: str,
        session_id: str,
        block: ContextBlock,
    ) -> None:
        """仅执行冷记忆归档。"""
        if self._observability:
            self._observability.record(
                "system",
                {
                    "event": "storage.context_block.archive",
                    "logic_id": logic_id,
                    "session_id": session_id,
                    "block_id": block.block_id,
                },
                "DEBUG",
            )
        if self._cold:
            await self._cold.archive_block(logic_id, session_id, block)

    async def read_context_snapshot(
        self,
        request: ContextLoadRequest,
    ) -> ContextLoadResult:
        """读取指定会话的上下文快照。"""
        if self._observability:
            self._observability.record(
                "system",
                {
                    "event": "storage.context_snapshot.read",
                    "logic_id": request.logic_id,
                    "session_id": request.session_id,
                    "budget": {
                        "max_input": request.budget.max_input_tokens if request.budget else None,
                        "reserved_output": request.budget.reserved_output_tokens if request.budget else None,
                    },
                },
                "DEBUG",
            )
        # 目前仅从热记忆读取，未来可在此处集成温记忆召回
        return await self._hot.read_context_snapshot(request)

    async def upsert_system_part(
        self,
        logic_id: str,
        session_id: str,
        part: SystemPromptPart,
    ) -> None:
        """更新系统提示词片段。"""
        if self._observability:
            self._observability.record(
                "system",
                {
                    "event": "storage.system_part.upsert",
                    "logic_id": logic_id,
                    "session_id": session_id,
                    "source": part.source,
                },
                "DEBUG",
            )
        await self._hot.upsert_system_part(logic_id, session_id, part)

    async def delete_context_history(self, logic_id: str, session_id: str) -> None:
        """删除会话历史。"""
        if self._observability:
            self._observability.record(
                "system",
                {
                    "event": "storage.context_history.delete",
                    "logic_id": logic_id,
                    "session_id": session_id,
                },
                "INFO",
            )
        await self._hot.delete_context_history(logic_id=logic_id, session_id=session_id)

    async def persist_runtime_state(
        self,
        logic_id: str,
        session_id: str,
        state: Mapping[str, JSONValue],
    ) -> dict[str, JSONValue]:
        """持久化运行时状态。"""
        if self._observability:
            self._observability.record(
                "system",
                {
                    "event": "storage.runtime_state.persist",
                    "logic_id": logic_id,
                    "session_id": session_id,
                },
                "DEBUG",
            )
        return await self._hot.persist_runtime_state(
            logic_id=logic_id,
            session_id=session_id,
            state=state,
        )

    async def load_runtime_state(self, logic_id: str, session_id: str) -> dict[str, JSONValue]:
        """加载运行时状态。"""
        return await self._hot.load_runtime_state(logic_id=logic_id, session_id=session_id)
