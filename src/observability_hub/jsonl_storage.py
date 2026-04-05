import json
import logging
import os
import time
from pathlib import Path
from src.observability_hub.recording import NormalizedRecord

logger = logging.getLogger(__name__)

class JSONLStorageEngine:
    """
    (OB-P0-04, OB-P0-05) 调试引擎实现与滚动清理。

    设计意图：
    将归一化后的 NormalizedRecord 持久化到 JSONL 文件中，并实现基于文件大小的日志滚动清理。
    """
    def __init__(self, log_dir: str = "logs", max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "debug_trace.jsonl"
        self.max_bytes = max_bytes
        self.backup_count = backup_count

    def write_record(self, record: NormalizedRecord) -> None:
        self._rotate_if_needed()
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                record_dict = {
                    "trace_id": record.trace_id,
                    "level": record.level.value,
                    "payload": record.payload,
                    "payload_type": record.payload_type,
                    "timestamp_ms": record.timestamp_ms
                }
                f.write(json.dumps(record_dict, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Failed to write JSONL log: {e}")

    def _rotate_if_needed(self) -> None:
        if not self.log_file.exists():
            return
        if self.log_file.stat().st_size < self.max_bytes:
            return

        # 简单的文件轮转 (Rolling over)
        for i in range(self.backup_count - 1, 0, -1):
            src = self.log_dir / f"debug_trace.jsonl.{i}"
            dst = self.log_dir / f"debug_trace.jsonl.{i + 1}"
            if src.exists():
                os.replace(src, dst)
        os.replace(self.log_file, self.log_dir / "debug_trace.jsonl.1")
