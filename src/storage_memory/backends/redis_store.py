import json
from collections.abc import Mapping
from typing import Any

from src.domain.context import (
    ContextBlock,
    ContextLoadRequest,
    ContextLoadResult,
    JSONValue,
    SystemPromptPart,
)
from ..contracts.protocols import HotMemoryProtocol
from ..internal.keys import _build_hot_key, _build_state_key, _build_sys_key
from ..internal.codecs import (
    dump_context_block,
    load_context_block,
    dump_system_prompt_part,
    load_system_prompt_part,
)


class RedisHotMemoryStore(HotMemoryProtocol):
    """基于 Redis 的热记忆与状态存储实现。

    该后端利用 Redis 的高效列表 (LIST)、哈希 (HASH) 和字符串 (STRING)
    结构，提供低延迟的对话上下文与运行时状态访问能力。
    """

    def __init__(
        self,
        redis_client: Any,
        max_blocks: int | None = 10,
        max_tokens: int | None = None,
    ) -> None:
        """初始化 RedisHotMemoryStore。"""
        if max_blocks is None and max_tokens is None:
            raise ValueError("At least one of max_blocks or max_tokens must be set")
            
        self._redis = redis_client
        self.max_blocks = max_blocks
        self.max_tokens = max_tokens

    async def append_context_block(
        self,
        logic_id: str,
        session_id: str,
        block: ContextBlock,
    ) -> None:
        """追加一条热记忆块到 Redis，并同步进行双重阈值（块数与 Token）裁剪。"""
        hot_key = _build_hot_key(logic_id=logic_id, session_id=session_id)
        
        # 1. 追加
        payload = json.dumps(dump_context_block(block))
        await self._redis.rpush(hot_key, payload)

        # 2. 裁剪
        # 2.1 获取列表内容
        raw_items = await self._redis.lrange(hot_key, 0, -1)
        items = [json.loads(item) for item in raw_items]

        # 2.2 双重裁剪计算
        keep_start = 0
        
        # 按块数初步裁剪
        if self.max_blocks is not None and len(items) > self.max_blocks:
            keep_start = len(items) - self.max_blocks
            items = items[keep_start:]
        
        # 按 Token 进一步裁剪
        if self.max_tokens is not None:
            current_tokens = 0
            token_keep_index = len(items)
            for i in range(len(items) - 1, -1, -1):
                token_count = int(items[i].get("token_count", 0))
                if current_tokens + token_count > self.max_tokens:
                    break
                current_tokens += token_count
                token_keep_index = i
            
            if token_keep_index > 0:
                keep_start += token_keep_index
                items = items[token_keep_index:]
        
        # 3. 执行物理裁剪
        if keep_start > 0:
            await self._redis.ltrim(hot_key, keep_start, -1)

    async def upsert_system_part(
        self,
        logic_id: str,
        session_id: str,
        part: SystemPromptPart,
    ) -> None:
        """更新系统提示词片段。"""
        sys_key = _build_sys_key(logic_id=logic_id, session_id=session_id)
        payload = json.dumps(dump_system_prompt_part(part))
        await self._redis.hset(sys_key, part.source, payload)

    async def read_context_snapshot(
        self,
        request: ContextLoadRequest,
    ) -> ContextLoadResult:
        """从 Redis 读取指定会话的完整上下文快照。"""
        hot_key = _build_hot_key(logic_id=request.logic_id, session_id=request.session_id)
        
        # 加载历史块
        limit = request.history_block_limit
        raw_items = await self._redis.lrange(hot_key, -limit, -1) if limit > 0 else await self._redis.lrange(hot_key, 0, -1)
        history_blocks = tuple(load_context_block(json.loads(raw)) for raw in raw_items)

        # 加载系统片段
        sys_key = _build_sys_key(logic_id=request.logic_id, session_id=request.session_id)
        raw_parts = await self._redis.hgetall(sys_key)
        system_parts = tuple(
            load_system_prompt_part(json.loads(raw)) for raw in raw_parts.values()
        )

        return ContextLoadResult(
            system_parts=system_parts, history_blocks=history_blocks
        )

    async def delete_context_history(self, logic_id: str, session_id: str) -> None:
        """删除会话历史。"""
        hot_key = _build_hot_key(logic_id=logic_id, session_id=session_id)
        await self._redis.delete(hot_key)
        sys_key = _build_sys_key(logic_id=logic_id, session_id=session_id)
        await self._redis.delete(sys_key)

    async def persist_runtime_state(
        self,
        logic_id: str,
        session_id: str,
        state: Mapping[str, JSONValue],
    ) -> dict[str, JSONValue]:
        """持久化运行时状态。"""
        state_key = _build_state_key(logic_id=logic_id, session_id=session_id)
        payload = dict(state)
        await self._redis.set(state_key, json.dumps(payload))
        return payload

    async def load_runtime_state(self, logic_id: str, session_id: str) -> dict[str, JSONValue]:
        """加载运行时状态。"""
        state_key = _build_state_key(logic_id=logic_id, session_id=session_id)
        raw_state = await self._redis.get(state_key)
        if raw_state:
            return json.loads(raw_state)
        return {}
