from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import threading
import time
from typing import Any
import uuid

try:
    from pydantic import BaseModel as PydanticBaseModel
except Exception:
    PydanticBaseModel = None


class LogLevel(str, Enum):
    """日志级别枚举，遵循标准 Syslog 规范"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class NormalizedRecord:
    """
    归一化后的监控记录实体。
    所有进入监控中心的异构数据（如字符串、嵌套字典、Pydantic模型），
    最终都会被拍平并转换为此结构，以便于后续持久化到 JSONL 或 Elasticsearch。
    """
    trace_id: str
    level: LogLevel
    payload: dict[str, Any]
    payload_type: str
    timestamp_ms: int


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


def record(
    trace_id: str,
    data: Mapping[str, Any] | str | Any,
    level: LogLevel | str = LogLevel.INFO,
) -> NormalizedRecord:
    """
    系统级数据打点与日志记录的统一入口。
    
    Args:
        trace_id: 必须携带的追踪ID，用于串联单次请求的所有日志
        data: 任意格式的原始数据（支持字符串、嵌套字典、BaseModel实例）
        level: 日志级别
        
    Returns:
        NormalizedRecord: 归一化后的记录实体
    """
    normalized_level = level if isinstance(level, LogLevel) else LogLevel(level)
    payload, payload_type = _normalize_data(data)
    return NormalizedRecord(
        trace_id=trace_id,
        level=normalized_level,
        payload=payload,
        payload_type=payload_type,
        timestamp_ms=int(time.time() * 1000),
    )


def _normalize_data(data: Mapping[str, Any] | str | Any) -> tuple[dict[str, Any], str]:
    """内部路由：根据数据类型，选择对应的归一化策略"""
    if isinstance(data, Mapping):
        return _flatten_mapping(data), "dict"
    if isinstance(data, str):
        return {"message": data}, "str"
    if _is_base_model_instance(data):
        serialized = _serialize_base_model(data)
        return _flatten_mapping(serialized), "basemodel"
    raise TypeError("unsupported_record_data_type")


def _is_base_model_instance(data: Any) -> bool:
    """鸭子类型检测：判断对象是否是一个 Pydantic BaseModel 或类似的结构化数据类"""
    if PydanticBaseModel is not None and isinstance(data, PydanticBaseModel):
        return True
    has_model_dump = callable(getattr(data, "model_dump", None))
    has_dict = callable(getattr(data, "dict", None))
    return has_model_dump or has_dict


def _serialize_base_model(data: Any) -> dict[str, Any]:
    """安全地将结构化模型转换为字典"""
    model_dump = getattr(data, "model_dump", None)
    if callable(model_dump):
        serialized = model_dump()
    else:
        dict_method = getattr(data, "dict", None)
        if not callable(dict_method):
            raise TypeError("invalid_basemodel_payload")
        serialized = dict_method()

    if not isinstance(serialized, Mapping):
        raise TypeError("basemodel_must_serialize_to_mapping")
    return dict(serialized)


def _flatten_mapping(
    data: Mapping[str, Any],
    parent_key: str = "",
) -> dict[str, Any]:
    """
    核心算法：字典展平 (Flatten Dictionary)。
    将深层嵌套的字典拍平为一维结构，例如：
    {"user": {"id": 1, "name": "foo"}} 转换为 {"user.id": 1, "user.name": "foo"}
    这种结构极大地提升了后续存储在 Elasticsearch 等搜索引擎时的检索效率。
    """
    flattened: dict[str, Any] = {}
    for key, value in data.items():
        key_str = str(key)
        composite_key = f"{parent_key}.{key_str}" if parent_key else key_str
        if isinstance(value, Mapping):
            flattened.update(_flatten_mapping(value, composite_key))
        else:
            flattened[composite_key] = value
    return flattened
