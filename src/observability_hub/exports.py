from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from src.observability_hub.recording import LogLevel, NormalizedRecord


@dataclass(frozen=True)
class ObservabilityHubExports:
    layer: str
    status: str
    trace_id_generator: Callable[[], str]
    record: Callable[[str, Mapping[str, Any] | str | Any, LogLevel | str], NormalizedRecord]
