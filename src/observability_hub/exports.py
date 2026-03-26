from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from src.observability_hub.recording import LogLevel, NormalizedRecord
from src.observability_hub.request_coloring import RequestColoringContext


@dataclass(frozen=True)
class ObservabilityHubExports:
    layer: str
    status: str
    trace_id_generator: Callable[[], str]
    record: Callable[[str, Mapping[str, Any] | str | Any, LogLevel | str], NormalizedRecord]
    is_request_colored: Callable[[RequestColoringContext], bool]
