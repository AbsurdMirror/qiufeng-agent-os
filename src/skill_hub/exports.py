from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from src.orchestration_engine.contracts import (
    CapabilityDescription,
    CapabilityHub,
    CapabilityRequest,
    CapabilityResult,
)


@dataclass(frozen=True)
class SkillHubExports:
    layer: str
    status: str

    capability_hub: CapabilityHub

    list_capabilities: Callable[[], tuple[CapabilityDescription, ...]]
    get_capability: Callable[[str], CapabilityDescription | None]
    invoke_capability: Callable[[CapabilityRequest], Awaitable[CapabilityResult]]
