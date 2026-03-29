from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from src.orchestration_engine.contracts import (
    CapabilityDescription,
    CapabilityHub,
    CapabilityRequest,
    CapabilityResult,
)
from src.skill_hub.browser_use import BrowserUsePyTool
from src.skill_hub.contracts import BrowserUseRuntimeState


@dataclass(frozen=True)
class SkillHubExports:
    layer: str
    status: str
    browser_pytool: BrowserUsePyTool
    capability_hub: CapabilityHub
    list_capabilities: Callable[[], tuple[CapabilityDescription, ...]]
    get_capability: Callable[[str], CapabilityDescription | None]
    probe_browser_runtime: Callable[[], BrowserUseRuntimeState]
    invoke_browser: Callable[[CapabilityRequest], Awaitable[CapabilityResult]]
    invoke_capability: Callable[[CapabilityRequest], Awaitable[CapabilityResult]]
