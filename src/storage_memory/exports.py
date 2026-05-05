from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from src.domain.context import (
    ContextBlock,
    ContextLoadRequest,
    ContextLoadResult,
    JSONValue,
    SystemPromptPart,
)
from .contracts.protocols import (
    ColdMemoryProtocol,
    HotMemoryCarrier,
    ProfileProtocol,
    StorageAccessProtocol,
    WarmMemoryProtocol,
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
    
    append_context_block: Callable[
        [str, str, ContextBlock, int],
        Awaitable[tuple[ContextBlock, ...]],
    ]
    archive_context_block: Callable[[str, str, ContextBlock], Awaitable[None]]
    read_context_snapshot: Callable[[ContextLoadRequest], Awaitable[ContextLoadResult]]
    upsert_system_part: Callable[[str, str, SystemPromptPart], Awaitable[None]]
    delete_context_history: Callable[[str, str], Awaitable[None]]
    persist_runtime_state: Callable[[str, str, Mapping[str, JSONValue]], Awaitable[dict[str, JSONValue]]]
    load_runtime_state: Callable[[str, str], Awaitable[dict[str, JSONValue]]]

    # T4 扩展：分级记忆协议预留
    warm_memory: WarmMemoryProtocol | None = None
    cold_memory: ColdMemoryProtocol | None = None
    profile: ProfileProtocol | None = None
