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
    """
    存储与记忆层的强类型模块导出容器。
    
    暴露了面向业务层的读写接口代理函数。
    """
    layer: str
    status: str
    carrier: HotMemoryCarrier
    protocol: StorageAccessProtocol
    append_hot_memory: Callable[[str, str, HotMemoryItem, int], tuple[HotMemoryItem, ...]]
    read_hot_memory: Callable[[str, str, int], tuple[HotMemoryItem, ...]]
    persist_runtime_state: Callable[[str, str, Mapping[str, Any]], dict[str, Any]]
    load_runtime_state: Callable[[str, str], dict[str, Any]]
