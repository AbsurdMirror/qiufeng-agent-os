from collections.abc import Mapping
from typing import Any

from src.storage_memory.contracts import (
    HotMemoryItem,
    InMemoryHotMemoryStore,
    StorageAccessProtocol,
)
from src.storage_memory.exports import StorageMemoryExports


def initialize() -> StorageMemoryExports:
    store = InMemoryHotMemoryStore()
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


def _append_hot_memory(
    protocol: StorageAccessProtocol,
    logic_id: str,
    session_id: str,
    item: HotMemoryItem,
    max_rounds: int = 10,
) -> tuple[HotMemoryItem, ...]:
    return protocol.append_hot_memory(
        logic_id=logic_id,
        session_id=session_id,
        item=item,
        max_rounds=max_rounds,
    )


def _read_hot_memory(
    protocol: StorageAccessProtocol,
    logic_id: str,
    session_id: str,
    limit: int = 10,
) -> tuple[HotMemoryItem, ...]:
    return protocol.read_hot_memory(logic_id=logic_id, session_id=session_id, limit=limit)


def _persist_runtime_state(
    protocol: StorageAccessProtocol,
    logic_id: str,
    session_id: str,
    state: Mapping[str, Any],
) -> dict[str, Any]:
    return protocol.persist_runtime_state(logic_id=logic_id, session_id=session_id, state=state)


def _load_runtime_state(
    protocol: StorageAccessProtocol,
    logic_id: str,
    session_id: str,
) -> dict[str, Any]:
    return protocol.load_runtime_state(logic_id=logic_id, session_id=session_id)
