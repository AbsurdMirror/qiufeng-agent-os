from collections.abc import Awaitable, Callable
from typing import Any

from src.domain.events import UniversalEvent
from src.channel_gateway.exports import ChannelGatewayExports
from src.observability_hub.exports import ObservabilityHubExports
from src.orchestration_engine.context.runtime_context import RuntimeContext
from src.orchestration_engine.contracts import CapabilityHub
from src.orchestration_engine.runtime.base_orchestrator import BaseOrchestrator
from src.qfaos.runtime.context_facade import DefaultQFAExecutionContext, DefaultQFASessionContext
from src.qfaos.runtime.contracts import QFAEvent
from src.storage_memory.exports import StorageMemoryExports


class CustomExecuteOrchestrator(BaseOrchestrator):
    """将用户 custom_execute 适配到 BaseOrchestrator 的桥接编排器。"""

    def __init__(
        self,
        *,
        execute_handler: Callable[[QFAEvent, DefaultQFAExecutionContext], Awaitable[None]],
        storage_memory: StorageMemoryExports,
        logic_id: str,
        channel_gateway: ChannelGatewayExports | None = None,
        observability: ObservabilityHubExports | None = None,
    ) -> None:
        self._execute_handler = execute_handler
        self._storage_memory = storage_memory
        self._logic_id = logic_id
        self._channel_gateway = channel_gateway
        self._observability = observability

    async def execute(
        self,
        event: UniversalEvent,
        ctx: RuntimeContext,
        capability_hub: CapabilityHub,
    ) -> dict[str, object]:
        sdk_event = QFAEvent.from_universal(event)
        session_ctx = DefaultQFASessionContext(
            runtime_context=ctx,
            capability_hub=capability_hub,
            storage_memory=self._storage_memory,
            logic_id=self._logic_id,
            event=event,
            channel_gateway=self._channel_gateway,
            observability=self._observability,
        )
        sdk_ctx = DefaultQFAExecutionContext(
            session_ctx=session_ctx,
            capability_hub=capability_hub,
        )
        try:
            await self._execute_handler(sdk_event, sdk_ctx)
        except Exception as exc:
            if self._observability is not None:
                self._observability.record(
                    ctx.trace_id,
                    {"event": "qfaos.custom_execute.error", "error": str(exc)},
                    "ERROR",
                )
            raise
        return dict(ctx.state)
