from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class HotMemoryItem:
    trace_id: str
    role: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class HotMemoryCarrier(Protocol):
    def lpush(self, key: str, value: Mapping[str, Any]) -> int:
        raise NotImplementedError

    def lrange(self, key: str, start: int, stop: int) -> tuple[dict[str, Any], ...]:
        raise NotImplementedError

    def ltrim(self, key: str, start: int, stop: int) -> None:
        raise NotImplementedError


class StorageAccessProtocol(Protocol):
    def append_hot_memory(
        self,
        logic_id: str,
        session_id: str,
        item: HotMemoryItem,
        max_rounds: int = 10,
    ) -> tuple[HotMemoryItem, ...]:
        raise NotImplementedError

    def read_hot_memory(
        self,
        logic_id: str,
        session_id: str,
        limit: int = 10,
    ) -> tuple[HotMemoryItem, ...]:
        raise NotImplementedError

    def persist_runtime_state(
        self,
        logic_id: str,
        session_id: str,
        state: Mapping[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError

    def load_runtime_state(self, logic_id: str, session_id: str) -> dict[str, Any]:
        raise NotImplementedError


class InMemoryHotMemoryStore(HotMemoryCarrier, StorageAccessProtocol):
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
    return f"hot_memory:{logic_id}:{session_id}"


def _build_state_key(logic_id: str, session_id: str) -> str:
    return f"runtime_state:{logic_id}:{session_id}"


def _dump_hot_memory_item(item: HotMemoryItem) -> dict[str, Any]:
    return {
        "trace_id": item.trace_id,
        "role": item.role,
        "content": item.content,
        "metadata": dict(item.metadata),
    }


def _load_hot_memory_item(payload: Mapping[str, Any]) -> HotMemoryItem:
    return HotMemoryItem(
        trace_id=str(payload.get("trace_id", "")),
        role=str(payload.get("role", "")),
        content=str(payload.get("content", "")),
        metadata=dict(payload.get("metadata", {})),
    )
