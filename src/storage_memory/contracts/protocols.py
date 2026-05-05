from collections.abc import Mapping
from typing import Protocol

from src.domain.context import (
    ContextBlock,
    ContextLoadRequest,
    ContextLoadResult,
    JSONValue,
    SystemPromptPart,
)


class HotMemoryCarrier(Protocol):
    """
    底层热记忆存储介质协议 (Duck Typing Interface)。
    抽象了类似于 Redis 的核心列表操作语义，允许后续无缝替换为真实的 Redis 客户端。
    """
    async def rpush(self, key: str, value: Mapping[str, object]) -> int:
        """向列表右侧（尾部）推入一条数据，返回推入后列表的长度"""
        raise NotImplementedError

    async def lpush(self, key: str, value: Mapping[str, object]) -> int:
        """向列表左侧（头部）推入一条数据，返回推入后列表的长度"""
        raise NotImplementedError

    async def lrange(self, key: str, start: int, stop: int) -> tuple[dict[str, object], ...]:
        """获取列表中指定范围的数据（支持负数索引，如 -1 表示末尾）"""
        raise NotImplementedError

    async def ltrim(self, key: str, start: int, stop: int) -> None:
        """修剪列表，仅保留指定范围内的元素（用于实现定长滑动窗口记忆）"""
        raise NotImplementedError


class StorageAccessProtocol(Protocol):
    """
    面向编排引擎层暴露的高层存储与记忆访问协议。
    屏蔽了底层的 Key 构造逻辑和序列化细节。
    """
    async def append_context_block(
        self,
        logic_id: str,
        session_id: str,
        block: ContextBlock,
        max_blocks: int,
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
