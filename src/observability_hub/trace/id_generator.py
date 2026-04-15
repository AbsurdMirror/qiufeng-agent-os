import threading
import time
import uuid

class GlobalTraceIDGenerator:
    """
    全局唯一 Trace ID 生成器。
    
    设计策略：时间戳(毫秒) + 进程内自增序列 + UUID随机字符串。
    这种设计既保证了在极端并发下的绝对唯一性，又保证了 Trace ID 具有
    时间排序属性（Lexicographically Sortable），对日志检索非常友好。
    """
    def __init__(self, prefix: str = "trace") -> None:
        self._prefix = prefix
        self._lock = threading.Lock()
        self._last_timestamp_ms = 0
        self._sequence = -1

    def generate(self) -> str:
        now_ms = int(time.time() * 1000)
        with self._lock:
            if now_ms == self._last_timestamp_ms:
                self._sequence += 1
            else:
                self._last_timestamp_ms = now_ms
                self._sequence = 0
            sequence = self._sequence
        random_part = uuid.uuid4().hex[:16]
        return f"{self._prefix}-{now_ms}-{sequence:06d}-{random_part}"


_GLOBAL_TRACE_ID_GENERATOR = GlobalTraceIDGenerator()


def generate_trace_id() -> str:
    """生成全局唯一的追踪 ID (Trace ID)"""
    return _GLOBAL_TRACE_ID_GENERATOR.generate()
