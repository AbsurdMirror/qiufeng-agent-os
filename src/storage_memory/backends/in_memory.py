from collections.abc import Mapping
from typing import Any
from src.domain.memory import HotMemoryItem
from ..contracts.protocols import HotMemoryCarrier, StorageAccessProtocol
from ..internal.keys import _build_hot_key, _build_state_key
from ..internal.codecs import _dump_hot_memory_item, _load_hot_memory_item


class InMemoryHotMemoryStore(HotMemoryCarrier, StorageAccessProtocol):
    """
    基于内存的热记忆与状态存储实现 (Mock Store)。
    主要用于 P0 T2 阶段的链路打通和本地测试，同时实现了 Carrier 和 Access 两层协议。
    """
    def __init__(self) -> None:
        self._hot_memory: dict[str, list[dict[str, Any]]] = {}
        self._runtime_states: dict[str, dict[str, Any]] = {}

    async def rpush(self, key: str, value: Mapping[str, Any]) -> int:
        queue = self._hot_memory.setdefault(key, [])
        queue.append(dict(value))
        return len(queue)

    async def lpush(self, key: str, value: Mapping[str, Any]) -> int:
        queue = self._hot_memory.setdefault(key, [])
        queue.insert(0, dict(value))
        return len(queue)

    async def lrange(self, key: str, start: int, stop: int) -> tuple[dict[str, Any], ...]:
        queue = self._hot_memory.get(key, [])
        normalized_stop = len(queue) - 1 if stop == -1 else stop
        if normalized_stop < start:
            return ()
        return tuple(dict(item) for item in queue[start : normalized_stop + 1])

    async def ltrim(self, key: str, start: int, stop: int) -> None:
        queue = self._hot_memory.get(key)
        if queue is None:
            return
        normalized_stop = len(queue) - 1 if stop == -1 else stop
        if normalized_stop < start:
            self._hot_memory[key] = []
            return
        self._hot_memory[key] = queue[start : normalized_stop + 1]

    async def append_hot_memory(
        self,
        logic_id: str,
        session_id: str,
        item: HotMemoryItem,
        max_rounds: int = 10,
    ) -> tuple[HotMemoryItem, ...]:
        hot_key = _build_hot_key(logic_id=logic_id, session_id=session_id)
        await self.rpush(hot_key, _dump_hot_memory_item(item))
        await self.ltrim(hot_key, -max_rounds, -1)
        return await self.read_hot_memory(logic_id=logic_id, session_id=session_id, limit=max_rounds)

    async def read_hot_memory(
        self,
        logic_id: str,
        session_id: str,
        limit: int = 10,
    ) -> tuple[HotMemoryItem, ...]:
        hot_key = _build_hot_key(logic_id=logic_id, session_id=session_id)
        raw_items = await self.lrange(hot_key, -limit, -1)
        return tuple(_load_hot_memory_item(raw_item) for raw_item in raw_items)

    async def persist_runtime_state(
        self,
        logic_id: str,
        session_id: str,
        state: Mapping[str, Any],
    ) -> dict[str, Any]:
        state_key = _build_state_key(logic_id=logic_id, session_id=session_id)
        payload = dict(state)
        self._runtime_states[state_key] = payload
        return dict(payload)

    async def load_runtime_state(self, logic_id: str, session_id: str) -> dict[str, Any]:
        state_key = _build_state_key(logic_id=logic_id, session_id=session_id)
        state = self._runtime_states.get(state_key, {})
        return dict(state)
