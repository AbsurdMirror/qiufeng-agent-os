from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from src.storage_memory.contracts import (
    HotMemoryCarrier,
    HotMemoryItem,
    StorageAccessProtocol,
)


@dataclass(frozen=True)
class StorageMemoryExports:
    layer: str
    status: str
    carrier: HotMemoryCarrier
    protocol: StorageAccessProtocol
    append_hot_memory: Callable[[str, str, HotMemoryItem, int], tuple[HotMemoryItem, ...]]
    read_hot_memory: Callable[[str, str, int], tuple[HotMemoryItem, ...]]
    persist_runtime_state: Callable[[str, str, Mapping[str, Any]], dict[str, Any]]
    load_runtime_state: Callable[[str, str], dict[str, Any]]
