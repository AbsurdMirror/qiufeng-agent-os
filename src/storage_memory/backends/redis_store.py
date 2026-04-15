import json
from collections.abc import Mapping
from typing import Any

from ..contracts.models import HotMemoryItem
from ..contracts.protocols import HotMemoryCarrier, StorageAccessProtocol
from ..internal.keys import _build_hot_key, _build_state_key
from ..internal.codecs import _dump_hot_memory_item, _load_hot_memory_item


class RedisHotMemoryStore(HotMemoryCarrier, StorageAccessProtocol):
    """
    基于 Redis 的热记忆与状态存储实现
    大白话解释：以前这个系统重启就必定失忆。
    现在这个类是一个专业的“外脑”，它通过 Redis 强行把咱们跟机器人的近场对话和参数状态钉死在内存数据库里。
    哪怕你重启了 Agent-OS 服务进程，用户连回来照样能接着上一句聊，完美实现了 T4 阶段的状态无损挂载。
    """
    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client

    async def rpush(self, key: str, value: Mapping[str, Any]) -> int:
        payload = json.dumps(dict(value))
        return await self._redis.rpush(key, payload)

    async def lpush(self, key: str, value: Mapping[str, Any]) -> int:
        payload = json.dumps(dict(value))
        return await self._redis.lpush(key, payload)

    async def lrange(self, key: str, start: int, stop: int) -> tuple[dict[str, Any], ...]:
        raw_items = await self._redis.lrange(key, start, stop)
        return tuple(json.loads(item) for item in raw_items)

    async def ltrim(self, key: str, start: int, stop: int) -> None:
        await self._redis.ltrim(key, start, stop)

    async def append_hot_memory(
        self,
        logic_id: str,
        session_id: str,
        item: HotMemoryItem,
        max_rounds: int = 10,
    ) -> tuple[HotMemoryItem, ...]:
        """SM-P0-02: 热记忆策略 - LIFO 最近 N 轮对话缓存"""
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
        """SM-P0-04: 上下文注入 (通过被动提供读取接口供编排引擎拉取)"""
        hot_key = _build_hot_key(logic_id=logic_id, session_id=session_id)
        raw_items = await self.lrange(hot_key, -limit, -1)
        return tuple(_load_hot_memory_item(raw_item) for raw_item in raw_items)

    async def persist_runtime_state(
        self,
        logic_id: str,
        session_id: str,
        state: Mapping[str, Any],
    ) -> dict[str, Any]:
        """SM-P0-03: 持久化存储 - 无损持久化运行时状态"""
        state_key = _build_state_key(logic_id=logic_id, session_id=session_id)
        payload = dict(state)
        await self._redis.set(state_key, json.dumps(payload))
        return payload

    async def load_runtime_state(self, logic_id: str, session_id: str) -> dict[str, Any]:
        state_key = _build_state_key(logic_id=logic_id, session_id=session_id)
        raw_state = await self._redis.get(state_key)
        if raw_state:
            return json.loads(raw_state)
        return {}
