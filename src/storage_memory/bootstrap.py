from collections.abc import Mapping
from typing import Any

from src.storage_memory.contracts import (
    HotMemoryItem,
    InMemoryHotMemoryStore,
    StorageAccessProtocol,
)
from src.storage_memory.exports import StorageMemoryExports


import asyncio
from src.storage_memory.redis_store import create_store

def initialize() -> StorageMemoryExports:
    """
    存储与记忆层 (Storage & Memory) 的初始化引导函数。
    
    此函数会被 `src.app.bootstrap` 在应用启动时调用。它负责：
    初始化底层的内存或Redis存储引擎，并将常用的记忆读写与状态持久化接口通过高阶函数代理暴露出去，
    从而将具体的 Store 实例封装在本层内部，不向上层泄漏。
    """

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # In a running loop, we can't cleanly run_until_complete inline
            # without nested loops, so we fallback to the memory store for now
            # or we could make initialize() async. Since initialize() is sync,
            # we just instantiate the memory store or fire and forget a task.
            # We'll use InMemoryHotMemoryStore directly if we can't block here.
            from src.storage_memory.contracts import InMemoryHotMemoryStore
            store = InMemoryHotMemoryStore()
        else:
            store = loop.run_until_complete(create_store())
    except RuntimeError:
        store = asyncio.run(create_store())

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
        ),
        read_hot_memory=lambda logic_id, session_id, limit=10: _read_hot_memory(
            protocol=store,
            logic_id=logic_id,
            session_id=session_id,
            limit=limit,
        ),
        persist_runtime_state=lambda logic_id, session_id, state: _persist_runtime_state(
            protocol=store,
            logic_id=logic_id,
            session_id=session_id,
            state=state,
        ),
        load_runtime_state=lambda logic_id, session_id: _load_runtime_state(
            protocol=store,
            logic_id=logic_id,
            session_id=session_id,
        ),
    )


async def _append_hot_memory(
    protocol: StorageAccessProtocol,
    logic_id: str,
    session_id: str,
    item: HotMemoryItem,
    max_rounds: int = 10,
) -> tuple[HotMemoryItem, ...]:
    """代理方法：追加热记忆"""
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
) -> tuple[HotMemoryItem, ...]:
    """代理方法：读取热记忆"""
    return await protocol.read_hot_memory(logic_id=logic_id, session_id=session_id, limit=limit)


async def _persist_runtime_state(
    protocol: StorageAccessProtocol,
    logic_id: str,
    session_id: str,
    state: Mapping[str, Any],
) -> dict[str, Any]:
    """代理方法：持久化状态字典"""
    return await protocol.persist_runtime_state(
        logic_id=logic_id,
        session_id=session_id,
        state=state,
    )


async def _load_runtime_state(
    protocol: StorageAccessProtocol,
    logic_id: str,
    session_id: str,
) -> dict[str, Any]:
    """代理方法：读取持久化的状态字典"""
    return await protocol.load_runtime_state(logic_id=logic_id, session_id=session_id)
