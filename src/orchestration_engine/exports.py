from collections.abc import Callable
from dataclasses import dataclass

from src.orchestration_engine.agent_registry import AgentRegistry, AgentSpec


@dataclass(frozen=True)
class OrchestrationEngineExports:
    layer: str
    status: str
    agent_registry: AgentRegistry
    register_agent: Callable[[AgentSpec], AgentSpec]
    query_agent: Callable[[str, str, str | None], AgentSpec | None]
