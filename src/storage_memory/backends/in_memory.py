from collections.abc import Mapping

from src.domain.context import (
    ContextBlock,
    ContextLoadRequest,
    ContextLoadResult,
    JSONValue,
    SystemPromptPart,
)

from ..contracts.protocols import HotMemoryCarrier, StorageAccessProtocol
from ..internal.codecs import (
    dump_context_block,
    load_context_block,
    dump_system_prompt_part,
    load_system_prompt_part,
)
from ..internal.keys import _build_hot_key, _build_state_key, _build_sys_key


class InMemoryHotMemoryStore(HotMemoryCarrier, StorageAccessProtocol):
    """
    基于内存的热记忆与状态存储实现 (Mock Store)。
    主要用于 P0 T2 阶段的链路打通和本地测试，同时实现了 Carrier 和 Access 两层协议。
    """
    def __init__(self) -> None:
        self._hot_memory: dict[str, list[dict[str, object]]] = {}
        self._runtime_states: dict[str, dict[str, JSONValue]] = {}
        self._system_parts: dict[str, dict[str, dict[str, object]]] = {}

    async def rpush(self, key: str, value: Mapping[str, object]) -> int:
        queue = self._hot_memory.setdefault(key, [])
        queue.append(dict(value))
        return len(queue)

    async def lpush(self, key: str, value: Mapping[str, object]) -> int:
        queue = self._hot_memory.setdefault(key, [])
        queue.insert(0, dict(value))
        return len(queue)

    async def lrange(self, key: str, start: int, stop: int) -> tuple[dict[str, object], ...]:
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

    async def append_context_block(
        self,
        logic_id: str,
        session_id: str,
        block: ContextBlock,
        max_blocks: int,
    ) -> tuple[ContextBlock, ...]:
        hot_key = _build_hot_key(logic_id=logic_id, session_id=session_id)
        await self.rpush(hot_key, dump_context_block(block))
        await self.ltrim(hot_key, -max_blocks, -1)
        
        # 为了兼容接口返回，我们重新读取快照中的 blocks
        snapshot = await self.read_context_snapshot(
            ContextLoadRequest(
                logic_id=logic_id,
                session_id=session_id,
                budget=None,  # type: ignore # InMemory 暂时忽略 budget
                include_profile_patch=False,
                include_memory_snippets=False,
                history_block_limit=max_blocks
            )
        )
        return snapshot.history_blocks

    async def upsert_system_part(
        self,
        logic_id: str,
        session_id: str,
        part: SystemPromptPart,
    ) -> None:
        sys_key = _build_sys_key(logic_id=logic_id, session_id=session_id)
        parts_map = self._system_parts.setdefault(sys_key, {})
        parts_map[part.source] = dump_system_prompt_part(part)

    async def read_context_snapshot(
        self,
        request: ContextLoadRequest,
    ) -> ContextLoadResult:
        hot_key = _build_hot_key(logic_id=request.logic_id, session_id=request.session_id)
        raw_items = await self.lrange(hot_key, -request.history_block_limit, -1)
        history_blocks = tuple(load_context_block(raw_item) for raw_item in raw_items)
        
        # 加载 System Parts
        sys_key = _build_sys_key(logic_id=request.logic_id, session_id=request.session_id)
        parts_map = self._system_parts.get(sys_key, {})
        system_parts = tuple(load_system_prompt_part(raw) for raw in parts_map.values())

        return ContextLoadResult(
            system_parts=system_parts,
            history_blocks=history_blocks
        )

    async def delete_context_history(self, logic_id: str, session_id: str) -> None:
        hot_key = _build_hot_key(logic_id=logic_id, session_id=session_id)
        if hot_key in self._hot_memory:
            del self._hot_memory[hot_key]
        
        sys_key = _build_sys_key(logic_id=logic_id, session_id=session_id)
        if sys_key in self._system_parts:
            del self._system_parts[sys_key]

    async def persist_runtime_state(
        self,
        logic_id: str,
        session_id: str,
        state: Mapping[str, JSONValue],
    ) -> dict[str, JSONValue]:
        state_key = _build_state_key(logic_id=logic_id, session_id=session_id)
        payload = dict(state)
        self._runtime_states[state_key] = payload
        return dict(payload)

    async def load_runtime_state(self, logic_id: str, session_id: str) -> dict[str, JSONValue]:
        state_key = _build_state_key(logic_id=logic_id, session_id=session_id)
        state = self._runtime_states.get(state_key, {})
        return dict(state)
