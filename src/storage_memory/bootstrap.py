from collections.abc import Mapping
from typing import Any

from src.domain.context import (
    ContextBlock,
    ContextLoadRequest,
    ContextLoadResult,
    JSONValue,
)
from .contracts.protocols import StorageAccessProtocol
from .exports import StorageMemoryExports
from src.observability_hub.exports import ObservabilityHubExports

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
        warm_memory=None,  # 预留
        cold_memory=None,  # 预留
        profile=None,      # 预留
        append_context_block=lambda logic_id, session_id, block, max_blocks=10: _append_context_block(
            protocol=store,
            logic_id=logic_id,
            session_id=session_id,
            block=block,
            max_blocks=max_blocks,
            observability=observability,
        ),
        read_context_snapshot=lambda request: _read_context_snapshot(
            protocol=store,
            request=request,
            observability=observability,
        ),
        delete_context_history=lambda logic_id, session_id: _delete_context_history(
            protocol=store,
            logic_id=logic_id,
            session_id=session_id,
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


async def _append_context_block(
    protocol: StorageAccessProtocol,
    logic_id: str,
    session_id: str,
    block: ContextBlock,
    max_blocks: int = 10,
    observability: ObservabilityHubExports | None = None,
) -> tuple[ContextBlock, ...]:
    """代理方法：追加上下文块"""
    if observability:
        # 记录块信息预览
        observability.record(
            "system",  # 块写入通常由编排层触发，若有 trace_id 更好，暂用 system
            {
                "event": "storage.context_block.append",
                "logic_id": logic_id,
                "session_id": session_id,
                "block_id": block.block_id,
                "kind": block.kind,
                "message_count": len(block.messages),
                "token_count": block.token_count,
            },
            "DEBUG",
        )
    return await protocol.append_context_block(
        logic_id=logic_id,
        session_id=session_id,
        block=block,
        max_blocks=max_blocks,
    )


async def _read_context_snapshot(
    protocol: StorageAccessProtocol,
    request: ContextLoadRequest,
    observability: ObservabilityHubExports | None = None,
) -> ContextLoadResult:
    """代理方法：读取上下文快照"""
    if observability:
        observability.record(
            "system",
            {
                "event": "storage.context_snapshot.read",
                "logic_id": request.logic_id,
                "session_id": request.session_id,
                "budget": {
                    "max_input": request.budget.max_input_tokens,
                    "reserved_output": request.budget.reserved_output_tokens,
                },
            },
            "DEBUG",
        )
    return await protocol.read_context_snapshot(request)


async def _delete_context_history(
    protocol: StorageAccessProtocol,
    logic_id: str,
    session_id: str,
    observability: ObservabilityHubExports | None = None,
) -> None:
    """代理方法：删除历史记忆"""
    if observability:
        observability.record(
            "system",
            {
                "event": "storage.context_history.delete",
                "logic_id": logic_id,
                "session_id": session_id,
            },
            "INFO",
        )
    await protocol.delete_context_history(logic_id=logic_id, session_id=session_id)


async def _persist_runtime_state(
    protocol: StorageAccessProtocol,
    logic_id: str,
    session_id: str,
    state: Mapping[str, JSONValue],
    observability: ObservabilityHubExports | None = None,
) -> dict[str, JSONValue]:
    """代理方法：持久化状态字典"""
    if observability:
        observability.record(
            "system",
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
) -> dict[str, JSONValue]:
    """代理方法：读取持久化的状态字典"""
    return await protocol.load_runtime_state(logic_id=logic_id, session_id=session_id)
