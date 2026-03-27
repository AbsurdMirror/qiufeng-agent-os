from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class HotMemoryItem:
    """
    单条热记忆（短期记忆）的数据载体模型。
    
    设计意图：
    用于在多轮对话中记录用户的输入、模型的输出以及工具的调用结果。
    它将被序列化后存入 Redis 的 List 结构中。
    
    Attributes:
        trace_id: 产生此条记忆的请求链路 ID。
        role: 角色标识（如 user, assistant, system）。
        content: 记忆的文本内容。
        metadata: 附加元数据（如 Token 消耗、时间戳等）。
    """
    trace_id: str
    role: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class HotMemoryCarrier(Protocol):
    """
    底层热记忆存储介质协议 (Duck Typing Interface)。
    抽象了类似于 Redis 的核心列表操作语义，允许后续无缝替换为真实的 Redis 客户端。
    """
    def lpush(self, key: str, value: Mapping[str, Any]) -> int:
        """向列表左侧（头部）推入一条数据，返回推入后列表的长度"""
        raise NotImplementedError

    def lrange(self, key: str, start: int, stop: int) -> tuple[dict[str, Any], ...]:
        """获取列表中指定范围的数据（支持负数索引，如 -1 表示末尾）"""
        raise NotImplementedError

    def ltrim(self, key: str, start: int, stop: int) -> None:
        """修剪列表，仅保留指定范围内的元素（用于实现定长滑动窗口记忆）"""
        raise NotImplementedError


class StorageAccessProtocol(Protocol):
    """
    面向编排引擎层暴露的高层存储与记忆访问协议。
    屏蔽了底层的 Key 构造逻辑和序列化细节。
    """
    def append_hot_memory(
        self,
        logic_id: str,
        session_id: str,
        item: HotMemoryItem,
        max_rounds: int = 10,
    ) -> tuple[HotMemoryItem, ...]:
        """追加一条热记忆，并自动进行滑动窗口截断，返回截断后的最新记忆列表"""
        raise NotImplementedError

    def read_hot_memory(
        self,
        logic_id: str,
        session_id: str,
        limit: int = 10,
    ) -> tuple[HotMemoryItem, ...]:
        """读取指定会话的热记忆历史记录"""
        raise NotImplementedError

    def persist_runtime_state(
        self,
        logic_id: str,
        session_id: str,
        state: Mapping[str, Any],
    ) -> dict[str, Any]:
        """持久化编排引擎的运行时状态（如 LangGraph 的 state 字典）"""
        raise NotImplementedError

    def load_runtime_state(self, logic_id: str, session_id: str) -> dict[str, Any]:
        """加载上次中断/挂起的运行时状态"""
        raise NotImplementedError


class InMemoryHotMemoryStore(HotMemoryCarrier, StorageAccessProtocol):
    """
    基于内存的热记忆与状态存储实现 (Mock Store)。
    主要用于 P0 T2 阶段的链路打通和本地测试，同时实现了 Carrier 和 Access 两层协议。
    """
    def __init__(self) -> None:
        self._hot_memory: dict[str, list[dict[str, Any]]] = {}
        self._runtime_states: dict[str, dict[str, Any]] = {}

    def lpush(self, key: str, value: Mapping[str, Any]) -> int:
        queue = self._hot_memory.setdefault(key, [])
        queue.insert(0, dict(value))
        return len(queue)

    def lrange(self, key: str, start: int, stop: int) -> tuple[dict[str, Any], ...]:
        queue = self._hot_memory.get(key, [])
        normalized_stop = len(queue) - 1 if stop == -1 else stop
        if normalized_stop < start:
            return ()
        return tuple(dict(item) for item in queue[start : normalized_stop + 1])

    def ltrim(self, key: str, start: int, stop: int) -> None:
        queue = self._hot_memory.get(key)
        if queue is None:
            return
        normalized_stop = len(queue) - 1 if stop == -1 else stop
        if normalized_stop < start:
            self._hot_memory[key] = []
            return
        self._hot_memory[key] = queue[start : normalized_stop + 1]

    def append_hot_memory(
        self,
        logic_id: str,
        session_id: str,
        item: HotMemoryItem,
        max_rounds: int = 10,
    ) -> tuple[HotMemoryItem, ...]:
        hot_key = _build_hot_key(logic_id=logic_id, session_id=session_id)
        self.lpush(hot_key, _dump_hot_memory_item(item))
        self.ltrim(hot_key, 0, max_rounds - 1)
        return self.read_hot_memory(logic_id=logic_id, session_id=session_id, limit=max_rounds)

    def read_hot_memory(
        self,
        logic_id: str,
        session_id: str,
        limit: int = 10,
    ) -> tuple[HotMemoryItem, ...]:
        hot_key = _build_hot_key(logic_id=logic_id, session_id=session_id)
        raw_items = self.lrange(hot_key, 0, limit - 1)
        return tuple(_load_hot_memory_item(raw_item) for raw_item in raw_items)

    def persist_runtime_state(
        self,
        logic_id: str,
        session_id: str,
        state: Mapping[str, Any],
    ) -> dict[str, Any]:
        state_key = _build_state_key(logic_id=logic_id, session_id=session_id)
        payload = dict(state)
        self._runtime_states[state_key] = payload
        return dict(payload)

    def load_runtime_state(self, logic_id: str, session_id: str) -> dict[str, Any]:
        state_key = _build_state_key(logic_id=logic_id, session_id=session_id)
        state = self._runtime_states.get(state_key, {})
        return dict(state)


def _build_hot_key(logic_id: str, session_id: str) -> str:
    """构建用于存储热记忆列表的唯一键名"""
    return f"hot_memory:{logic_id}:{session_id}"


def _build_state_key(logic_id: str, session_id: str) -> str:
    """构建用于存储运行时状态字典的唯一键名"""
    return f"runtime_state:{logic_id}:{session_id}"


def _dump_hot_memory_item(item: HotMemoryItem) -> dict[str, Any]:
    """将强类型的数据载体序列化为可存储的普通字典"""
    return {
        "trace_id": item.trace_id,
        "role": item.role,
        "content": item.content,
        "metadata": dict(item.metadata),
    }


def _load_hot_memory_item(payload: Mapping[str, Any]) -> HotMemoryItem:
    """从普通字典反序列化出强类型的数据载体，提供容错保护"""
    return HotMemoryItem(
        trace_id=str(payload.get("trace_id", "")),
        role=str(payload.get("role", "")),
        content=str(payload.get("content", "")),
        metadata=dict(payload.get("metadata", {})),
    )

