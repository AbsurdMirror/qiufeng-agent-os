"""
编排引擎层 (Orchestration Engine) 模块入口。

P0.5 T2 阶段：内部已重组至子目录，本文件只从新路径聚合导出。
"""
from .bootstrap import initialize
from .runtime.base_orchestrator import BaseOrchestrator
from .registry.agent_registry import (
    AgentCapabilityMap,
    AgentIdentity,
    AgentOrchestrator,
    AgentRegistry,
    AgentSpec,
    InMemoryAgentRegistry,
)
from .contracts import (
    CapabilityDescription,
    CapabilityHub,
    CapabilityRequest,
    CapabilityResult,
    NullCapabilityHub,
)
from .exports import OrchestrationEngineExports
from .context.runtime_context import RuntimeContext
from .context.state_context_manager import StateContextManager
from .runtime.langgraph_runtime import LangGraphRuntime, LangGraphExecutable

__all__ = [
    "AgentCapabilityMap",
    "AgentIdentity",
    "AgentOrchestrator",
    "AgentRegistry",
    "AgentSpec",
    "InMemoryAgentRegistry",
    "BaseOrchestrator",
    "CapabilityDescription",
    "CapabilityHub",
    "CapabilityRequest",
    "CapabilityResult",
    "NullCapabilityHub",
    "RuntimeContext",
    "LangGraphRuntime",
    "LangGraphExecutable",
    "OrchestrationEngineExports",
    "StateContextManager",
    "initialize",
]
