from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from src.orchestration_engine.contracts import (
    CapabilityDescription,
    CapabilityHub,
    CapabilityRequest,
    CapabilityResult,
)
from src.skill_hub.builtin_tools.browser_use import BrowserUsePyTool
from .contracts import BrowserUseRuntimeState


@dataclass(frozen=True)
class SkillHubExports:
    layer: str
    status: str

    browser_pytool: BrowserUsePyTool
    capability_hub: CapabilityHub

    list_capabilities: Callable[[], tuple[CapabilityDescription, ...]]
    get_capability: Callable[[str], CapabilityDescription | None]
    invoke_capability: Callable[[CapabilityRequest], Awaitable[CapabilityResult]]

    probe_browser_runtime: Callable[[], BrowserUseRuntimeState]
    invoke_browser: Callable[[CapabilityRequest], Awaitable[CapabilityResult]]
