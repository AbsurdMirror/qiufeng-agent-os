from dataclasses import dataclass, field
from typing import Any, Protocol

from src.domain.capabilities import CapabilityDescription, CapabilityRequest, CapabilityResult


@dataclass(frozen=True)
class PyToolDefinition:
    capability: CapabilityDescription
    metadata: dict[str, Any] = field(default_factory=dict)


class PyTool(Protocol):
    capability: CapabilityDescription

    async def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        raise NotImplementedError
