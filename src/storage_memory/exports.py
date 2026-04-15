from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .contracts.models import HotMemoryItem
from .contracts.protocols import HotMemoryCarrier, StorageAccessProtocol


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
    append_hot_memory: Callable[
        [str, str, HotMemoryItem, int],
        Awaitable[tuple[HotMemoryItem, ...]],
    ]
    read_hot_memory: Callable[[str, str, int], Awaitable[tuple[HotMemoryItem, ...]]]
    persist_runtime_state: Callable[[str, str, Mapping[str, Any]], Awaitable[dict[str, Any]]]
    load_runtime_state: Callable[[str, str], Awaitable[dict[str, Any]]]
