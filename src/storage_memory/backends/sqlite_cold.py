import sqlite3
import json
import asyncio
from pathlib import Path
from typing import Any

from src.domain.context import ContextBlock, JSONValue
from src.storage_memory.contracts.protocols import ColdMemoryProtocol
from src.storage_memory.internal.codecs import dump_context_block


class SQLiteColdMemory(ColdMemoryProtocol):
    """
    基于 SQLite 的冷记忆（归档）后端。
    负责将所有对话上下文块持久化到本地数据库，不进行裁剪，作为兜底归档。
    """

    def __init__(self, db_path: str | Path = ".storage/cold_memory.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库表结构"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS context_archives (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    logic_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    block_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_session ON context_archives(logic_id, session_id)"
            )
            conn.commit()

    async def archive_block(
        self,
        logic_id: str,
        session_id: str,
        block: ContextBlock,
    ) -> None:
        """归档一个上下文块"""
        payload = dump_context_block(block)
        
        def _sync_insert():
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO context_archives (logic_id, session_id, block_id, kind, payload_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        logic_id,
                        session_id,
                        block.block_id,
                        block.kind,
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )
                conn.commit()

        await asyncio.to_thread(_sync_insert)

    async def get_facts(self, logic_id: str, user_id: str) -> dict[str, JSONValue]:
        """【预留】从冷记忆中提取事实"""
        # 暂时返回空，后续可接入 LLM 提取逻辑
        return {}

    async def query_history(
        self,
        logic_id: str,
        session_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """查询归档的历史记录（内部或调试使用）"""
        def _sync_query():
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT block_id, kind, payload_json, created_at 
                    FROM context_archives 
                    WHERE logic_id = ? AND session_id = ? 
                    ORDER BY id ASC 
                    LIMIT ?
                    """,
                    (logic_id, session_id, limit),
                )
                return [dict(row) for row in cursor.fetchall()]

        return await asyncio.to_thread(_sync_query)
