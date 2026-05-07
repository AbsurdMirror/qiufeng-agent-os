import asyncio
from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import Field

from src.domain.context import (
    ContextBlock,
    ContextLoadRequest,
    ContextLoadResult,
    JSONValue,
    SystemPromptPart,
)
from src.domain.decorators import qfaos_pytool
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

    @qfaos_pytool("storage.append_block")
    async def append_context_block(
        self,
        logic_id: Annotated[str, Field(description="业务逻辑 ID")],
        session_id: Annotated[str, Field(description="会话 ID")],
        block: Annotated[ContextBlock, Field(description="要追加的逻辑原子块")],
    ) -> Annotated[None, Field(description="无返回值")]:
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
        await self._hot.append_context_block(
            logic_id=logic_id,
            session_id=session_id,
            block=block,
        )

        # 2. 同步归档到冷记忆 (全量记录)
        if self._cold:
            await self._cold.archive_block(logic_id, session_id, block)

    @qfaos_pytool("storage.archive_block")
    async def archive_context_block(
        self,
        logic_id: Annotated[str, Field(description="业务逻辑 ID")],
        session_id: Annotated[str, Field(description="会话 ID")],
        block: Annotated[ContextBlock, Field(description="要归档的逻辑原子块")],
    ) -> Annotated[None, Field(description="无返回值")]:
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

    @qfaos_pytool("storage.read_snapshot")
    async def read_context_snapshot(
        self,
        request: Annotated[ContextLoadRequest, Field(description="上下文加载请求，包含 Token 预算与范围")],
    ) -> Annotated[ContextLoadResult, Field(description="包含系统提示词片段与历史对话块的聚合结果")]:
        """读取指定会话的上下文快照，集成热记忆、温记忆召回与画像注入。"""
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

        # 1. 并发获取各级记忆
        # 1.1 从热记忆读取基础快照 (含 System Parts 和 History Blocks)
        hot_snapshot_task = asyncio.create_task(self._hot.read_context_snapshot(request))

        # 1.2 如果需要画像补丁且画像模块可用
        profile_task = None
        if request.include_profile_patch and self._profile:
            # 注意：profile 接口通常需要 user_id，此处暂时假设逻辑层能通过 session 获取
            profile_task = asyncio.create_task(self._profile.get_profile(request.session_id))

        # 1.3 如果需要温记忆召回且温记忆模块可用
        warm_task = None
        if request.include_memory_snippets and self._warm:
            # 温记忆召回通常基于某种 query，此处简化处理或需从上下文提取
            # 目前暂时预留逻辑
            pass

        # 2. 等待结果并聚合
        hot_result = await hot_snapshot_task
        final_system_parts = list(hot_result.system_parts)

        if profile_task:
            try:
                profile_data = await profile_task
                if profile_data:
                    final_system_parts.append(
                        SystemPromptPart(source="profile_patch", content=str(profile_data))
                    )
            except Exception:
                # 降级处理：画像获取失败不影响主流程
                pass

        return ContextLoadResult(
            system_parts=tuple(final_system_parts),
            history_blocks=hot_result.history_blocks,
        )

    @qfaos_pytool("storage.upsert_system_part")
    async def upsert_system_part(
        self,
        logic_id: Annotated[str, Field(description="业务逻辑 ID")],
        session_id: Annotated[str, Field(description="会话 ID")],
        part: Annotated[SystemPromptPart, Field(description="要更新或插入的系统提示词片段")],
    ) -> Annotated[None, Field(description="无返回值")]:
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

    @qfaos_pytool("storage.delete_history")
    async def delete_context_history(
        self,
        logic_id: Annotated[str, Field(description="业务逻辑 ID")],
        session_id: Annotated[str, Field(description="会话 ID")],
    ) -> Annotated[None, Field(description="无返回值")]:
        """全量清理会话历史（包含热、温、冷记忆）。"""
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
        
        # 并发执行清理任务
        tasks = [self._hot.delete_context_history(logic_id=logic_id, session_id=session_id)]
        
        if self._warm:
            tasks.append(self._warm.delete_history(logic_id=logic_id, session_id=session_id))
        
        if self._cold:
            tasks.append(self._cold.delete_history(logic_id=logic_id, session_id=session_id))
            
        await asyncio.gather(*tasks, return_exceptions=True)

    @qfaos_pytool("storage.persist_state")
    async def persist_runtime_state(
        self,
        logic_id: Annotated[str, Field(description="业务逻辑 ID")],
        session_id: Annotated[str, Field(description="会话 ID")],
        state: Annotated[Mapping[str, JSONValue], Field(description="需要持久化的运行时状态字典")],
    ) -> Annotated[dict[str, JSONValue], Field(description="保存成功的状态字典副本")]:
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

    @qfaos_pytool("storage.load_state")
    async def load_runtime_state(
        self,
        logic_id: Annotated[str, Field(description="业务逻辑 ID")],
        session_id: Annotated[str, Field(description="会话 ID")],
    ) -> Annotated[dict[str, JSONValue], Field(description="加载出的运行时状态字典，若不存在则返回空字典")]:
        """加载运行时状态。"""
        return await self._hot.load_runtime_state(logic_id=logic_id, session_id=session_id)
