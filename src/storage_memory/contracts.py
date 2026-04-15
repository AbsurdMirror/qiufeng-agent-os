"""
P0.5 兼容性 Re-export 模块
将旧路径导入重定向到新目录结构，确保平滑迁移。
"""

from .contracts.models import HotMemoryItem
from .contracts.protocols import HotMemoryCarrier, StorageAccessProtocol
from .backends.in_memory import InMemoryHotMemoryStore
from .internal.keys import _build_hot_key, _build_state_key
from .internal.codecs import _dump_hot_memory_item, _load_hot_memory_item

__all__ = [
    "HotMemoryItem",
    "HotMemoryCarrier",
    "StorageAccessProtocol",
    "InMemoryHotMemoryStore",
    "_build_hot_key",
    "_build_state_key",
    "_dump_hot_memory_item",
    "_load_hot_memory_item",
]
