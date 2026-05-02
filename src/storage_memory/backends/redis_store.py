import json
from collections.abc import Mapping
from typing import Any

from src.domain.context import (
    ContextBlock,
    ContextLoadRequest,
    ContextLoadResult,
    JSONValue,
)
from ..contracts.protocols import HotMemoryCarrier, StorageAccessProtocol
from ..internal.keys import _build_hot_key, _build_state_key
from ..internal.codecs import (
    dump_context_block,
    load_context_block,
)


class RedisHotMemoryStore(HotMemoryCarrier, StorageAccessProtocol):
    """
    基于 Redis 的热记忆与状态存储实现
    """
    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client

    async def rpush(self, key: str, value: Mapping[str, object]) -> int:
        payload = json.dumps(dict(value))
        return await self._redis.rpush(key, payload)

    async def lpush(self, key: str, value: Mapping[str, object]) -> int:
        payload = json.dumps(dict(value))
        return await self._redis.lpush(key, payload)

    async def lrange(self, key: str, start: int, stop: int) -> tuple[dict[str, object], ...]:
        raw_items = await self._redis.lrange(key, start, stop)
        return tuple(json.loads(item) for item in raw_items)

    async def ltrim(self, key: str, start: int, stop: int) -> None:
        await self._redis.ltrim(key, start, stop)

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
        
        snapshot = await self.read_context_snapshot(
            ContextLoadRequest(
                logic_id=logic_id,
                session_id=session_id,
                budget=None,  # type: ignore
                include_profile_patch=False,
                include_memory_snippets=False,
                history_block_limit=max_blocks
            )
        )
        return snapshot.history_blocks

    async def read_context_snapshot(
        self,
        request: ContextLoadRequest,
    ) -> ContextLoadResult:
        hot_key = _build_hot_key(logic_id=request.logic_id, session_id=request.session_id)
        raw_items = await self.lrange(hot_key, -request.history_block_limit, -1)
        history_blocks = tuple(load_context_block(raw_item) for raw_item in raw_items)
        
        return ContextLoadResult(
            system_parts=(),
            history_blocks=history_blocks
        )

    async def delete_context_history(self, logic_id: str, session_id: str) -> None:
        """删除指定会话的所有历史记忆记录"""
        hot_key = _build_hot_key(logic_id=logic_id, session_id=session_id)
        await self._redis.delete(hot_key)

    async def persist_runtime_state(
        self,
        logic_id: str,
        session_id: str,
        state: Mapping[str, JSONValue],
    ) -> dict[str, JSONValue]:
        state_key = _build_state_key(logic_id=logic_id, session_id=session_id)
        payload = dict(state)
        await self._redis.set(state_key, json.dumps(payload))
        return payload

    async def load_runtime_state(self, logic_id: str, session_id: str) -> dict[str, JSONValue]:
        state_key = _build_state_key(logic_id=logic_id, session_id=session_id)
        raw_state = await self._redis.get(state_key)
        if raw_state:
            return json.loads(raw_state)
        return {}
