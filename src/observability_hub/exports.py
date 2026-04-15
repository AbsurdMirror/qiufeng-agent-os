from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .record.recording import LogLevel, NormalizedRecord
from .coloring.request_coloring import RequestColoringContext, RequestColoringState
from .jsonl.storage import JSONLStorageEngine
from .cli.tailer import CLILogTailer


@dataclass(frozen=True)
class ObservabilityHubExports:
    layer: str
    status: str
    trace_id_generator: Callable[[], str]
    record: Callable[[str, Mapping[str, Any] | str | Any, LogLevel | str], NormalizedRecord]
    is_request_colored: Callable[[RequestColoringContext, RequestColoringState | None], bool]
    jsonl_storage: JSONLStorageEngine | None = None
    cli_logger: CLILogTailer | None = None
