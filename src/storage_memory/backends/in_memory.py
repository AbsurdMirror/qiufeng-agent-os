from collections.abc import Mapping

from src.domain.context import (
    ContextBlock,
    ContextLoadRequest,
    ContextLoadResult,
    JSONValue,
    SystemPromptPart,
)

from ..contracts.protocols import HotMemoryProtocol
from ..internal.codecs import (
    dump_context_block,
    load_context_block,
    dump_system_prompt_part,
    load_system_prompt_part,
)
from ..internal.keys import _build_hot_key, _build_state_key, _build_sys_key


class InMemoryHotMemoryStore(HotMemoryProtocol):
    """基于内存的热记忆与状态存储实现 (Mock Store)。"""

    def __init__(
        self,
        max_blocks: int | None = 10,
        max_tokens: int | None = None,
    ) -> None:
        """初始化 InMemoryHotMemoryStore。"""
        if max_blocks is None and max_tokens is None:
            raise ValueError("At least one of max_blocks or max_tokens must be set")
        
        self.max_blocks = max_blocks
        self.max_tokens = max_tokens
        
        self._hot_memory: dict[str, list[dict[str, object]]] = {}
        self._runtime_states: dict[str, dict[str, JSONValue]] = {}
        self._system_parts: dict[str, dict[str, dict[str, object]]] = {}

    async def append_context_block(
        self,
        logic_id: str,
        session_id: str,
        block: ContextBlock,
    ) -> tuple[ContextBlock, ...]:
        """追加一条热记忆块，并自动进行双重阈值（块数与 Token）裁剪。"""
        hot_key = _build_hot_key(logic_id=logic_id, session_id=session_id)
        queue = self._hot_memory.setdefault(hot_key, [])

        # 1. 追加新块
        queue.append(dump_context_block(block))

        # 2. 双重裁剪逻辑
        # 2.1 按块数裁剪
        if self.max_blocks is not None and len(queue) > self.max_blocks:
            queue[:] = queue[-self.max_blocks:]

        # 2.2 按 Token 裁剪
        if self.max_tokens is not None:
            current_tokens = 0
            keep_index = len(queue)
            # 从新到旧累加 Token
            for i in range(len(queue) - 1, -1, -1):
                token_count = int(queue[i].get("token_count", 0))
                if current_tokens + token_count > self.max_tokens:
                    break
                current_tokens += token_count
                keep_index = i
            
            if keep_index > 0:
                queue[:] = queue[keep_index:]

        # 3. 返回最新历史
        return tuple(load_context_block(item) for item in queue)

    async def upsert_system_part(
        self,
        logic_id: str,
        session_id: str,
        part: SystemPromptPart,
    ) -> None:
        """更新或插入系统提示词片段。"""
        sys_key = _build_sys_key(logic_id=logic_id, session_id=session_id)
        parts_map = self._system_parts.setdefault(sys_key, {})
        parts_map[part.source] = dump_system_prompt_part(part)

    async def read_context_snapshot(
        self,
        request: ContextLoadRequest,
    ) -> ContextLoadResult:
        """读取指定会话的上下文快照。"""
        hot_key = _build_hot_key(
            logic_id=request.logic_id, session_id=request.session_id
        )
        queue = self._hot_memory.get(hot_key, [])
        
        limit = request.history_block_limit
        raw_items = queue[-limit:] if limit > 0 else queue
        history_blocks = tuple(load_context_block(raw_item) for raw_item in raw_items)

        sys_key = _build_sys_key(
            logic_id=request.logic_id, session_id=request.session_id
        )
        parts_map = self._system_parts.get(sys_key, {})
        system_parts = tuple(
            load_system_prompt_part(raw) for raw in parts_map.values()
        )

        return ContextLoadResult(
            system_parts=system_parts, history_blocks=history_blocks
        )

    async def delete_context_history(self, logic_id: str, session_id: str) -> None:
        """删除指定会话的所有热记忆和系统片段。"""
        hot_key = _build_hot_key(logic_id=logic_id, session_id=session_id)
        self._hot_memory.pop(hot_key, None)

        sys_key = _build_sys_key(logic_id=logic_id, session_id=session_id)
        self._system_parts.pop(sys_key, None)

    async def persist_runtime_state(
        self,
        logic_id: str,
        session_id: str,
        state: Mapping[str, JSONValue],
    ) -> dict[str, JSONValue]:
        """持久化运行时状态字典。"""
        state_key = _build_state_key(logic_id=logic_id, session_id=session_id)
        payload = dict(state)
        self._runtime_states[state_key] = payload
        return dict(payload)

    async def load_runtime_state(
        self, logic_id: str, session_id: str
    ) -> dict[str, JSONValue]:
        """加载上次持久化的运行时状态。"""
        state_key = _build_state_key(logic_id=logic_id, session_id=session_id)
        state = self._runtime_states.get(state_key, {})
        return dict(state)
