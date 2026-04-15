from dataclasses import dataclass, field
from typing import Any, Protocol

from src.orchestration_engine.contracts import (
    CapabilityDescription,
    CapabilityRequest,
    CapabilityResult,
)


@dataclass(frozen=True)
class BrowserUseRuntimeState:
    browser_use_installed: bool
    playwright_installed: bool
    available: bool
    status: str
    reason: str | None = None
    browser_use_version: str | None = None
    playwright_version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "browser_use_installed": self.browser_use_installed,
            "playwright_installed": self.playwright_installed,
            "available": self.available,
            "status": self.status,
            "reason": self.reason,
            "browser_use_version": self.browser_use_version,
            "playwright_version": self.playwright_version,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PyToolDefinition:
    capability: CapabilityDescription
    runtime_state: BrowserUseRuntimeState
    metadata: dict[str, Any] = field(default_factory=dict)


class PyTool(Protocol):
    capability: CapabilityDescription

    def probe_runtime(self) -> BrowserUseRuntimeState:
        raise NotImplementedError

    async def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        raise NotImplementedError
