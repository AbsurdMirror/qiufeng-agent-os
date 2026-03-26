from dataclasses import dataclass
from typing import Any

from src.orchestration_engine.base_orchestrator import BaseOrchestrator


@dataclass(frozen=True)
class LangGraphExecutable:
    entrypoint: str
    compiled_graph: Any | None


class LangGraphRuntime:
    def load_orchestrator(self, orchestrator: BaseOrchestrator) -> BaseOrchestrator:
        return orchestrator

    def compile_entrypoint(self, entrypoint: str) -> LangGraphExecutable:
        if not entrypoint.strip():
            raise ValueError("invalid_langgraph_entrypoint")
        return LangGraphExecutable(entrypoint=entrypoint, compiled_graph=None)
