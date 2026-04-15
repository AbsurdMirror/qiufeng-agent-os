from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .registry.agent_registry import AgentRegistry, AgentSpec
from .contracts import CapabilityDescription, CapabilityHub, CapabilityRequest, CapabilityResult
from .runtime.langgraph_runtime import LangGraphRuntime


@dataclass(frozen=True)
class OrchestrationEngineExports:
    layer: str
    status: str

    agent_registry: AgentRegistry
    langgraph_runtime: LangGraphRuntime
    capability_hub: CapabilityHub

    register_agent: Callable[[AgentSpec], AgentSpec]
    query_agent: Callable[[str, str, str | None], AgentSpec | None]

    list_capabilities: Callable[[], tuple[CapabilityDescription, ...]]
    get_capability: Callable[[str], CapabilityDescription | None]
    invoke_capability: Callable[[CapabilityRequest], Awaitable[CapabilityResult]]

    context_manager: Any
