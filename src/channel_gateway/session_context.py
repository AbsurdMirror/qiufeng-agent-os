import hashlib
import time
import uuid
from typing import Dict, Optional
from threading import Lock

class SessionContextController:
    """
    会话上下文控制器 (Session Context Controller)
    实现 T4 阶段的 GW-P0-05 (身份映射) 和 GW-P0-06 (消息去重)
    """
    def __init__(self, deduplication_window_ms: int = 5000):
        self._id_mapping: Dict[str, str] = {}
        self._id_lock = Lock()

        # 消息去重: 存储 message_id -> timestamp (ms)
        self._processed_messages: Dict[str, int] = {}
        self._msg_lock = Lock()
        self._deduplication_window_ms = deduplication_window_ms

    def get_logical_uuid(self, platform_id: str) -> str:
        """
        GW-P0-05: 身份映射 (ID Mapping)
        将物理 ID (如飞书的 open_id) 映射到逻辑 UUID
        """
        with self._id_lock:
            if platform_id not in self._id_mapping:
                self._id_mapping[platform_id] = str(uuid.uuid4())
            return self._id_mapping[platform_id]

    def is_duplicate(self, message_id: str, current_timestamp_ms: Optional[int] = None) -> bool:
        """
        GW-P0-06: 消息去重 (Message Deduplication)
        检查 message_id 是否在防重窗口内被处理过
        """
        if current_timestamp_ms is None:
            current_timestamp_ms = int(time.time() * 1000)

        with self._msg_lock:
            # 清理过期的记录
            cutoff_time = current_timestamp_ms - self._deduplication_window_ms
            expired_keys = [
                k for k, v in self._processed_messages.items()
                if v < cutoff_time
            ]
            for k in expired_keys:
                del self._processed_messages[k]

            if message_id in self._processed_messages:
                return True

            self._processed_messages[message_id] = current_timestamp_ms
            return False

session_context_controller = SessionContextController()
