from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from src.observability_hub.recording import LogLevel, NormalizedRecord
from src.observability_hub.request_coloring import RequestColoringContext, RequestColoringState


@dataclass(frozen=True)
class ObservabilityHubExports:
    """
    全栈监控与治理中心的强类型模块导出容器。
    
    暴露了日志打点、TraceID 生成以及请求染色判定的核心能力。
    """
    layer: str
    status: str
    trace_id_generator: Callable[[], str]
    record: Callable[[str, Mapping[str, Any] | str | Any, LogLevel | str], NormalizedRecord]
    is_request_colored: Callable[[RequestColoringContext, RequestColoringState | None], bool]
