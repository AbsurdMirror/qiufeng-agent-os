import hashlib
import time
import uuid
from typing import Dict, Optional
from threading import Lock

class SessionContextController:
    """
    会话上下文控制器 (Session Context Controller)
    实现 T4 阶段的 GW-P0-05 (身份映射) 和 GW-P0-06 (消息去重)
    该控制器以单例模式运行在网关层，负责跨渠道的统一身份标识映射与防重扫荡。
    """
    def __init__(self, deduplication_window_ms: int = 5000):
        # 身份映射：存储物理平台ID到逻辑系统UUID的映射 (仅基于内存)
        self._id_mapping: Dict[str, str] = {}
        # 读写身份映射字典时使用的对象级互斥锁
        self._id_lock = Lock()

        # 消息去重: 存储 message_id -> timestamp (ms)
        self._processed_messages: Dict[str, int] = {}
        self._msg_lock = Lock()
        self._deduplication_window_ms = deduplication_window_ms

    def get_logical_uuid(self, platform_id: str) -> str:
        """
        GW-P0-05: 身份映射 (ID Mapping)
        将物理 ID (如飞书的 open_id) 映射到系统内部统一的逻辑 UUID。
        注意：当前完全基于内存实现，服务重启后相同平台ID会被分配不同的逻辑UUID。
        
        Args:
            platform_id (str): 外部渠道传入的用户物理ID，如 'ou_12345'
            
        Returns:
            str: Agent-OS 侧生成的统一逻辑 UUID 标识
        """
        with self._id_lock:
            if platform_id not in self._id_mapping:
                self._id_mapping[platform_id] = str(uuid.uuid4())
            return self._id_mapping[platform_id]

    def is_duplicate(self, message_id: str, current_timestamp_ms: Optional[int] = None) -> bool:
        """
        GW-P0-06: 消息去重 (Message Deduplication)
        检查指定 message_id 是否在防重窗口(默认5秒)内被处理过。
        
        Args:
            message_id (str): 渠道传入的消息唯一标识
            current_timestamp_ms (Optional[int]): 当前调用时间戳(毫秒)，用于测试注入或对齐时间
            
        Returns:
            bool: 返回 True 则表示该消息为重复消息，已被处理或正在被处理
        """
        if current_timestamp_ms is None:
            current_timestamp_ms = int(time.time() * 1000)

        with self._msg_lock:
            # 第一阶段：全面清理过期的记录以释放内存并滑动窗口
            cutoff_time = current_timestamp_ms - self._deduplication_window_ms
            
            # 性能风险预警：在数据量大时，遍历完整字典获取 items 会拖慢主线程
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
