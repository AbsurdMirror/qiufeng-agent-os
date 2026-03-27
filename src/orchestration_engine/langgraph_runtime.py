from dataclasses import dataclass
from typing import Any

from src.orchestration_engine.base_orchestrator import BaseOrchestrator


@dataclass(frozen=True)
class LangGraphExecutable:
    """
    LangGraph 编译后的可执行图包装器。
    
    Attributes:
        entrypoint: 原始的入口路径字符串。
        compiled_graph: 实际的 langgraph.graph.CompiledGraph 对象（由于 P0 T2 未引入 langgraph，暂为 Any）。
    """
    entrypoint: str
    compiled_graph: Any | None


class LangGraphRuntime:
    """
    基于 LangGraph 的编排引擎运行时加载器骨架。
    
    设计意图：
    负责将基于 LangGraph 定义的图（Graph）代码，动态加载并编译为系统可执行的 Orchestrator。
    目前处于 P0 T2 占位阶段，仅实现骨架接口。
    """
    def load_orchestrator(self, orchestrator: BaseOrchestrator) -> BaseOrchestrator:
        """
        加载并校验编排器实例。
        未来可在此处注入依赖（如 ModelProviderClient）。
        """
        return orchestrator

    def compile_entrypoint(self, entrypoint: str) -> LangGraphExecutable:
        """
        根据字符串入口路径（例如 'src.workflows.assistant:build_graph'），
        动态导入并编译 LangGraph 图。
        """
        if not entrypoint.strip():
            raise ValueError("invalid_langgraph_entrypoint")
        return LangGraphExecutable(entrypoint=entrypoint, compiled_graph=None)

