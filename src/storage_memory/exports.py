from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from src.domain.context import (
    ContextBlock,
    ContextLoadRequest,
    ContextLoadResult,
    JSONValue,
    SystemPromptPart,
)
from .internal.manager import StorageMemoryManager


@dataclass(frozen=True)
class StorageMemoryExports:
    """
    存储与记忆层的强类型模块导出容器。
    
    内部持有一个统一的 StorageMemoryManager 实例，并暴露其核心调度方法。
    """
    layer: str
    status: str
    
    # 核心管理类实例
    manager: StorageMemoryManager
    
    # 快捷调用接口 (直接引用自 manager)
    append_context_block: Callable[
        [str, str, ContextBlock],
        Awaitable[tuple[ContextBlock, ...]],
    ]
    archive_context_block: Callable[[str, str, ContextBlock], Awaitable[None]]
    read_context_snapshot: Callable[[ContextLoadRequest], Awaitable[ContextLoadResult]]
    upsert_system_part: Callable[[str, str, SystemPromptPart], Awaitable[None]]
    delete_context_history: Callable[[str, str], Awaitable[None]]
    persist_runtime_state: Callable[[str, str, Mapping[str, JSONValue]], Awaitable[dict[str, JSONValue]]]
    load_runtime_state: Callable[[str, str], Awaitable[dict[str, JSONValue]]]
