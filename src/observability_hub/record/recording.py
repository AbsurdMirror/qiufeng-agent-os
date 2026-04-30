from collections.abc import Mapping
from dataclasses import dataclass, is_dataclass, asdict
from enum import Enum
import time
from typing import Any

from pydantic import BaseModel as PydanticBaseModel


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


def record(
    trace_id: str,
    data: Any,
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
    if not isinstance(level, LogLevel):
        try:
            level = LogLevel(str(level).upper())
        except Exception as exc:
            raise ValueError(format_user_facing_error(exc, summary=f"日志级别 {level} 无效，必须为 {LogLevel.__members__.keys()} 中的一个"))
    payload, payload_type = _normalize_data(data)
    return NormalizedRecord(
        trace_id=trace_id,
        level=level,
        payload=payload,
        payload_type=payload_type,
        timestamp_ms=int(time.time() * 1000),
    )

def _any_to_mapping(data: Any) -> Mapping[str, Any]:
    """将任意数据转换为字典格式"""
    if isinstance(data, Mapping):
        return data
    if is_dataclass(data):
        return asdict(data)
    if isinstance(data, PydanticBaseModel):
        return data.model_dump()
    if isinstance(data, list):
        res = {}
        for idx, item in enumerate(data):
            res[f"{idx}"] = _any_to_mapping(item)
        return res
    return {"v": f"{data}"}

def _normalize_data(data: Any) -> tuple[dict[str, str], str]:
    """内部路由：根据数据类型，选择对应的归一化策略"""
    mapping_data = _any_to_mapping(data)
    return _flatten_mapping(mapping_data), f"{type(data)}"

def _flatten_mapping(
    data: Mapping[str, Any],
    parent_key: str = "",
) -> dict[str, str]:
    """
    核心算法：字典展平 (Flatten Dictionary)。
    将深层嵌套的字典拍平为一维结构，例如：
    {"user": {"id": 1, "name": "foo"}} 转换为 {"user.id": 1, "user.name": "foo"}
    这种结构极大地提升了后续存储在 Elasticsearch 等搜索引擎时的检索效率。
    """
    flattened: dict[str, str] = {}
    for key, value in data.items():
        composite_key = f"{parent_key}.{key}" if parent_key else key
        if isinstance(value, str):
            flattened[composite_key] = value
            continue
        mapping_value = _any_to_mapping(value)
        flattened.update(_flatten_mapping(mapping_value, composite_key))

    return flattened