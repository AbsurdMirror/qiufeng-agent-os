from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from src.domain.capabilities import CapabilityDescription, CapabilityRequest, CapabilityResult
from src.orchestration_engine.contracts import CapabilityHub


@dataclass(frozen=True)
class SkillHubExports:
    layer: str
    status: str

    capability_hub: CapabilityHub

    list_capabilities: Callable[[], tuple[CapabilityDescription, ...]]
    get_capability: Callable[[str], CapabilityDescription | None]
    invoke_capability: Callable[[CapabilityRequest], Awaitable[CapabilityResult]]
