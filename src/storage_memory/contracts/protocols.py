from collections.abc import Mapping
from typing import Any, Protocol
from src.domain.memory import HotMemoryItem


class HotMemoryCarrier(Protocol):
    """
    底层热记忆存储介质协议 (Duck Typing Interface)。
    抽象了类似于 Redis 的核心列表操作语义，允许后续无缝替换为真实的 Redis 客户端。
    """
    async def rpush(self, key: str, value: Mapping[str, Any]) -> int:
        """向列表右侧（尾部）推入一条数据，返回推入后列表的长度"""
        raise NotImplementedError

    async def lpush(self, key: str, value: Mapping[str, Any]) -> int:
        """向列表左侧（头部）推入一条数据，返回推入后列表的长度"""
        raise NotImplementedError

    async def lrange(self, key: str, start: int, stop: int) -> tuple[dict[str, Any], ...]:
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
    async def append_hot_memory(
        self,
        logic_id: str,
        session_id: str,
        item: HotMemoryItem,
        max_rounds: int = 10,
    ) -> tuple[HotMemoryItem, ...]:
        """追加一条热记忆，并自动进行滑动窗口截断，返回截断后的最新记忆列表"""
        raise NotImplementedError

    async def read_hot_memory(
        self,
        logic_id: str,
        session_id: str,
        limit: int = 10,
    ) -> tuple[HotMemoryItem, ...]:
        """读取指定会话的热记忆历史记录"""
        raise NotImplementedError

    async def persist_runtime_state(
        self,
        logic_id: str,
        session_id: str,
        state: Mapping[str, Any],
    ) -> dict[str, Any]:
        """持久化编排引擎的运行时状态（如 LangGraph 的 state 字典）"""
        raise NotImplementedError

    async def load_runtime_state(self, logic_id: str, session_id: str) -> dict[str, Any]:
        """加载上次中断/挂起的运行时状态"""
        raise NotImplementedError
