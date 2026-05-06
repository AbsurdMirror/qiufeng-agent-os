from collections.abc import Mapping
from typing import Protocol

from src.domain.context import (
    ContextBlock,
    ContextLoadRequest,
    ContextLoadResult,
    JSONValue,
    SystemPromptPart,
)


class HotMemoryProtocol(Protocol):
    """
    热记忆存储协议。
    负责管理最近的对话上下文，通常具有滑动窗口裁剪特性（基于块数和 Token 长度）。
    """
    max_blocks: int | None
    max_tokens: int | None

    async def append_context_block(
        self,
        logic_id: str,
        session_id: str,
        block: ContextBlock,
    ) -> tuple[ContextBlock, ...]:
        """追加一条热记忆块，并自动进行滑动窗口截断，返回截断后的最新块列表"""
        raise NotImplementedError

    async def upsert_system_part(
        self,
        logic_id: str,
        session_id: str,
        part: SystemPromptPart,
    ) -> None:
        """更新或插入系统提示词片段（如 base_prompt）"""
        raise NotImplementedError

    async def read_context_snapshot(
        self,
        request: ContextLoadRequest,
    ) -> ContextLoadResult:
        """读取指定会话的上下文快照（含 System Parts 和 History Blocks）"""
        raise NotImplementedError

    async def delete_context_history(self, logic_id: str, session_id: str) -> None:
        """删除指定会话的所有历史记忆记录"""
        raise NotImplementedError

    async def persist_runtime_state(
        self,
        logic_id: str,
        session_id: str,
        state: Mapping[str, JSONValue],
    ) -> dict[str, JSONValue]:
        """持久化编排引擎的运行时状态"""
        raise NotImplementedError

    async def load_runtime_state(self, logic_id: str, session_id: str) -> dict[str, JSONValue]:
        """加载上次中断/挂起的运行时状态"""
        raise NotImplementedError


class WarmMemoryProtocol(Protocol):
    """温记忆协议 (向量检索) - 预留"""
    async def search_snippets(self, logic_id: str, query: str, limit: int) -> tuple[str, ...]:
        raise NotImplementedError


class ColdMemoryProtocol(Protocol):
    """冷记忆协议 (长期归档/事实)"""

    async def archive_block(
        self,
        logic_id: str,
        session_id: str,
        block: ContextBlock,
    ) -> None:
        """归档一个上下文块到长期存储（冷记忆）"""
        raise NotImplementedError

    async def get_facts(self, logic_id: str, user_id: str) -> dict[str, JSONValue]:
        raise NotImplementedError


class ProfileProtocol(Protocol):
    """画像协议 (用户特征) - 预留"""
    async def get_profile(self, user_id: str) -> dict[str, JSONValue]:
        raise NotImplementedError
