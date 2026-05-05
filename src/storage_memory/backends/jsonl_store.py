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
from ..contracts.protocols import HotMemoryCarrier, StorageAccessProtocol
from ..internal.keys import _build_hot_key, _build_state_key, _build_sys_key
from ..internal.codecs import (
    dump_context_block,
    load_context_block,
    dump_system_prompt_part,
    load_system_prompt_part,
)


class JSONLHotMemoryStore(HotMemoryCarrier, StorageAccessProtocol):
    """
    基于 JSONL (JSON Lines) 文件的热记忆与状态存储实现。
    适用于本地开发环境，提供持久化能力而无需部署 Redis。
    """

    def __init__(self, base_dir: str | Path = ".storage") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_path_from_key(self, key: str) -> Path:
        """将 Redis 风格的 key 映射为文件路径"""
        # key 格式通常为 "prefix:logic_id:session_id"
        parts = key.split(":")
        if len(parts) >= 3:
            prefix, logic_id, session_id = parts[0], parts[1], parts[2]
            # 创建子目录: base_dir/prefix/logic_id/session_id.jsonl
            path = self.base_dir / prefix / logic_id / f"{session_id}.jsonl"
        else:
            # 降级处理
            path = self.base_dir / f"{key.replace(':', '_')}.jsonl"
        
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    async def rpush(self, key: str, value: Mapping[str, object]) -> int:
        path = self._get_path_from_key(key)
        
        def _sync_rpush():
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(dict(value), ensure_ascii=False) + "\n")
            # 计算行数
            with open(path, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)

        return await asyncio.to_thread(_sync_rpush)

    async def lpush(self, key: str, value: Mapping[str, object]) -> int:
        path = self._get_path_from_key(key)

        def _sync_lpush():
            lines = []
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            
            lines.insert(0, json.dumps(dict(value), ensure_ascii=False) + "\n")
            
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            return len(lines)

        return await asyncio.to_thread(_sync_lpush)

    async def lrange(self, key: str, start: int, stop: int) -> tuple[dict[str, object], ...]:
        path = self._get_path_from_key(key)

        def _sync_lrange():
            if not path.exists():
                return ()
            
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # 处理 stop 为 -1 的情况
            total = len(lines)
            actual_start = start if start >= 0 else max(0, total + start)
            actual_stop = stop if stop >= 0 else (total + stop)
            
            subset = lines[actual_start : actual_stop + 1]
            return tuple(json.loads(line) for line in subset if line.strip())

        return await asyncio.to_thread(_sync_lrange)

    async def ltrim(self, key: str, start: int, stop: int) -> None:
        path = self._get_path_from_key(key)

        def _sync_ltrim():
            if not path.exists():
                return
            
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            total = len(lines)
            actual_start = start if start >= 0 else max(0, total + start)
            actual_stop = stop if stop >= 0 else (total + stop)
            
            trimmed = lines[actual_start : actual_stop + 1]
            
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(trimmed)

        await asyncio.to_thread(_sync_ltrim)

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

    async def upsert_system_part(
        self,
        logic_id: str,
        session_id: str,
        part: SystemPromptPart,
    ) -> None:
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
        hot_key = _build_hot_key(logic_id=request.logic_id, session_id=request.session_id)
        raw_items = await self.lrange(hot_key, -request.history_block_limit, -1)
        history_blocks = tuple(load_context_block(raw_item) for raw_item in raw_items)
        
        # 加载 System Parts
        sys_key = _build_sys_key(logic_id=request.logic_id, session_id=request.session_id)
        path = self._get_path_from_key(sys_key).with_suffix(".json")
        
        def _sync_load_parts():
            if not path.exists():
                return ()
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return tuple(load_system_prompt_part(raw) for raw in data.values())
        
        system_parts = await asyncio.to_thread(_sync_load_parts)

        return ContextLoadResult(
            system_parts=system_parts,
            history_blocks=history_blocks
        )

    async def delete_context_history(self, logic_id: str, session_id: str) -> None:
        """删除指定会话的所有历史记忆记录"""
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
        state_key = _build_state_key(logic_id=logic_id, session_id=session_id)
        path = self._get_path_from_key(state_key)
        # 运行时状态通常是 json 而不是 jsonl
        path = path.with_suffix(".json")
        
        payload = dict(state)
        
        def _sync_persist():
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            return payload

        return await asyncio.to_thread(_sync_persist)

    async def load_runtime_state(self, logic_id: str, session_id: str) -> dict[str, JSONValue]:
        state_key = _build_state_key(logic_id=logic_id, session_id=session_id)
        path = self._get_path_from_key(state_key)
        path = path.with_suffix(".json")

        def _sync_load():
            if not path.exists():
                return {}
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

        return await asyncio.to_thread(_sync_load)
