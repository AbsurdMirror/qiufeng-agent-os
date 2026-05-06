from typing import Any

from .exports import StorageMemoryExports
from .backends.sqlite_cold import SQLiteColdMemory
from .internal.manager import StorageMemoryManager
from src.observability_hub.exports import ObservabilityHubExports

from .factory.create_store import create_store


def initialize(
    memory_config: Any | None = None,
    observability: ObservabilityHubExports | None = None,
) -> StorageMemoryExports:
    """
    存储与记忆层 (Storage & Memory) 的初始化引导函数。
    
    负责初始化各层级存储后端，并实例化统一的 StorageMemoryManager 调度器。
    """

    # 1. 初始化各存储层级后端
    store = create_store(config=memory_config)
    cold_store = SQLiteColdMemory()

    # 2. 实例化统一管理调度器
    manager = StorageMemoryManager(
        hot=store,
        cold=cold_store,
        observability=observability,
    )

    # 3. 构造导出容器
    return StorageMemoryExports(
        layer="storage_memory",
        status="initialized",
        manager=manager,
        append_context_block=manager.append_context_block,
        archive_context_block=manager.archive_context_block,
        read_context_snapshot=manager.read_context_snapshot,
        upsert_system_part=manager.upsert_system_part,
        delete_context_history=manager.delete_context_history,
        persist_runtime_state=manager.persist_runtime_state,
        load_runtime_state=manager.load_runtime_state,
    )
