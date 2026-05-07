import json
import os
import asyncio
from pathlib import Path
from collections.abc import Mapping

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


class JSONLHotMemoryStore(HotMemoryProtocol):
    """基于 JSONL (JSON Lines) 文件的热记忆与状态存储实现。

    适用于本地开发环境，提供持久化能力而无需部署 Redis。
    """

    def __init__(
        self,
        base_dir: str | Path = ".storage",
        max_blocks: int | None = 10,
        max_tokens: int | None = None,
    ) -> None:
        """初始化 JSONLHotMemoryStore。"""
        if max_blocks is None and max_tokens is None:
            raise ValueError("At least one of max_blocks or max_tokens must be set")
            
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.max_blocks = max_blocks
        self.max_tokens = max_tokens

    def _get_path_from_key(self, key: str) -> Path:
        """将 Redis 风格的 key 映射为本地文件路径。"""
        parts = key.split(":")
        if len(parts) >= 3:
            prefix, logic_id, session_id = parts[0], parts[1], parts[2]
            path = self.base_dir / prefix / logic_id / f"{session_id}.jsonl"
        else:
            path = self.base_dir / f"{key.replace(':', '_')}.jsonl"

        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    async def append_context_block(
        self,
        logic_id: str,
        session_id: str,
        block: ContextBlock,
    ) -> None:
        """追加一条热记忆块到 JSONL 文件，并执行双重阈值裁剪。"""
        hot_key = _build_hot_key(logic_id=logic_id, session_id=session_id)
        path = self._get_path_from_key(hot_key)
        payload = dump_context_block(block)

        def _sync_append():
            # 1. 读取现有内容
            items = []
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            items.append(json.loads(line))

            # 2. 追加
            items.append(payload)

            # 3. 双重裁剪
            # 3.1 按块数裁剪
            if self.max_blocks is not None and len(items) > self.max_blocks:
                items = items[-self.max_blocks :]

            # 3.2 按 Token 裁剪
            if self.max_tokens is not None:
                current_tokens = 0
                keep_index = len(items)
                for i in range(len(items) - 1, -1, -1):
                    token_count = items[i].get("token_count", 0)
                    if current_tokens + token_count > self.max_tokens:
                        break
                    current_tokens += token_count
                    keep_index = i

                if keep_index > 0:
                    items = items[keep_index:]

            # 4. 写回
            with open(path, "w", encoding="utf-8") as f:
                for item in items:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")

        await asyncio.to_thread(_sync_append)

    async def upsert_system_part(
        self,
        logic_id: str,
        session_id: str,
        part: SystemPromptPart,
    ) -> None:
        """更新系统提示词片段。"""
        sys_key = _build_sys_key(logic_id=logic_id, session_id=session_id)
        path = self._get_path_from_key(sys_key).with_suffix(".json")

        def _sync_upsert():
            data = {}
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data[part.source] = dump_system_prompt_part(part)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        await asyncio.to_thread(_sync_upsert)

    async def read_context_snapshot(
        self,
        request: ContextLoadRequest,
    ) -> ContextLoadResult:
        """读取上下文快照。"""
        hot_key = _build_hot_key(logic_id=request.logic_id, session_id=request.session_id)
        path = self._get_path_from_key(hot_key)
        
        def _sync_load():
            # 加载历史块
            history_blocks = []
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                limit = request.history_block_limit
                subset = lines[-limit:] if limit > 0 else lines
                history_blocks = [load_context_block(json.loads(line)) for line in subset if line.strip()]
            
            # 加载系统片段
            sys_key = _build_sys_key(logic_id=request.logic_id, session_id=request.session_id)
            sys_path = self._get_path_from_key(sys_key).with_suffix(".json")
            system_parts = []
            if sys_path.exists():
                with open(sys_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    system_parts = [load_system_prompt_part(raw) for raw in data.values()]
            
            return ContextLoadResult(
                system_parts=tuple(system_parts),
                history_blocks=tuple(history_blocks)
            )

        return await asyncio.to_thread(_sync_load)

    async def delete_context_history(self, logic_id: str, session_id: str) -> None:
        """删除会话历史文件。"""
        hot_key = _build_hot_key(logic_id=logic_id, session_id=session_id)
        path = self._get_path_from_key(hot_key)
        sys_key = _build_sys_key(logic_id=logic_id, session_id=session_id)
        sys_path = self._get_path_from_key(sys_key).with_suffix(".json")

        def _sync_delete():
            if path.exists():
                os.remove(path)
            if sys_path.exists():
                os.remove(sys_path)

        await asyncio.to_thread(_sync_delete)

    async def persist_runtime_state(
        self,
        logic_id: str,
        session_id: str,
        state: Mapping[str, JSONValue],
    ) -> dict[str, JSONValue]:
        """持久化运行时状态。"""
        state_key = _build_state_key(logic_id=logic_id, session_id=session_id)
        path = self._get_path_from_key(state_key).with_suffix(".json")
        payload = dict(state)

        def _sync_persist():
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            return payload

        return await asyncio.to_thread(_sync_persist)

    async def load_runtime_state(self, logic_id: str, session_id: str) -> dict[str, JSONValue]:
        """加载运行时状态。"""
        state_key = _build_state_key(logic_id=logic_id, session_id=session_id)
        path = self._get_path_from_key(state_key).with_suffix(".json")

        def _sync_load():
            if not path.exists():
                return {}
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

        return await asyncio.to_thread(_sync_load)
