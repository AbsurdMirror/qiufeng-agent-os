from abc import ABC, abstractmethod
from typing import Any

from src.channel_gateway.events import UniversalEvent
from src.orchestration_engine.runtime_context import RuntimeContext


class BaseOrchestrator(ABC):
    @abstractmethod
    async def execute(
        self,
        event: UniversalEvent,
        ctx: RuntimeContext,
        capability_hub: Any,
    ) -> dict[str, Any]:
        raise NotImplementedError
