from collections.abc import Mapping
from typing import Any

from src.domain.memory import HotMemoryItem
from .contracts.protocols import StorageAccessProtocol
from .exports import StorageMemoryExports
from src.observability_hub.exports import ObservabilityHubExports

import asyncio
from .factory.create_store import create_store

def initialize(
    memory_config: Any | None = None,
    observability: ObservabilityHubExports | None = None,
) -> StorageMemoryExports:
    """
    存储与记忆层 (Storage & Memory) 的初始化引导函数。
    
    此函数会被 `src.app.bootstrap` 在应用启动时调用。它负责：
    初始化底层的内存或Redis存储引擎，并将常用的记忆读写与状态持久化接口通过高阶函数代理暴露出去，
    从而将具体的 Store 实例封装在本层内部，不向上层泄漏。
    """

    store = create_store(config=memory_config)

    return StorageMemoryExports(
        layer="storage_memory",
        status="initialized",
        carrier=store,
        protocol=store,
        append_hot_memory=lambda logic_id, session_id, item, max_rounds=10: _append_hot_memory(
            protocol=store,
            logic_id=logic_id,
            session_id=session_id,
            item=item,
            max_rounds=max_rounds,
            observability=observability,
        ),
        read_hot_memory=lambda logic_id, session_id, limit=10: _read_hot_memory(
            protocol=store,
            logic_id=logic_id,
            session_id=session_id,
            limit=limit,
            observability=observability,
        ),
        persist_runtime_state=lambda logic_id, session_id, state: _persist_runtime_state(
            protocol=store,
            logic_id=logic_id,
            session_id=session_id,
            state=state,
            observability=observability,
        ),
        load_runtime_state=lambda logic_id, session_id: _load_runtime_state(
            protocol=store,
            logic_id=logic_id,
            session_id=session_id,
            observability=observability,
        ),
    )


async def _append_hot_memory(
    protocol: StorageAccessProtocol,
    logic_id: str,
    session_id: str,
    item: HotMemoryItem,
    max_rounds: int = 10,
    observability: ObservabilityHubExports | None = None,
) -> tuple[HotMemoryItem, ...]:
    """代理方法：追加热记忆"""
    if observability:
        observability.record(
            item.trace_id,
            {
                "event": "storage.hot_memory.append",
                "logic_id": logic_id,
                "session_id": session_id,
                "role": item.role,
                "content_preview": item.content[:100],
            },
            "DEBUG",
        )
    return await protocol.append_hot_memory(
        logic_id=logic_id,
        session_id=session_id,
        item=item,
        max_rounds=max_rounds,
    )


async def _read_hot_memory(
    protocol: StorageAccessProtocol,
    logic_id: str,
    session_id: str,
    limit: int = 10,
    observability: ObservabilityHubExports | None = None,
) -> tuple[HotMemoryItem, ...]:
    """代理方法：读取热记忆"""
    # 注意：读取时可能没有上下文 TraceID，此处不做强制记录，或者仅记录动作
    return await protocol.read_hot_memory(logic_id=logic_id, session_id=session_id, limit=limit)


async def _persist_runtime_state(
    protocol: StorageAccessProtocol,
    logic_id: str,
    session_id: str,
    state: Mapping[str, Any],
    observability: ObservabilityHubExports | None = None,
) -> dict[str, Any]:
    """代理方法：持久化状态字典"""
    if observability:
        # 尝试从状态或全局寻找 trace_id (由于 persist 通常在最后，这里可以记录)
        trace_id = "unknown"
        if isinstance(state, Mapping) and "trace_id" in state:
            trace_id = str(state["trace_id"])
            
        observability.record(
            trace_id,
            {
                "event": "storage.runtime_state.persist",
                "logic_id": logic_id,
                "session_id": session_id,
            },
            "DEBUG",
        )
    return await protocol.persist_runtime_state(
        logic_id=logic_id,
        session_id=session_id,
        state=state,
    )


async def _load_runtime_state(
    protocol: StorageAccessProtocol,
    logic_id: str,
    session_id: str,
    observability: ObservabilityHubExports | None = None,
) -> dict[str, Any]:
    """代理方法：读取持久化的状态字典"""
    return await protocol.load_runtime_state(logic_id=logic_id, session_id=session_id)
