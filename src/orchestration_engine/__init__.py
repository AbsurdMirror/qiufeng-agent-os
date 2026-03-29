"""
编排引擎层 (Orchestration Engine) 模块入口。

设计意图：
作为该层对外的唯一暴露点（Facade Pattern，外观模式），将内部散落的类和方法在这里统一导入并导出。
外部模块（如 app 层或其他层）只需要 `from src.orchestration_engine import initialize, BaseOrchestrator`，
而不需要关心这些类具体在哪个子文件中（如 `from src.orchestration_engine.contracts import ...`）。
这样即使内部文件结构重构，只要这里的导出列表不变，外部代码就不需要修改。

初学者提示：
`__all__` 列表明确指定了当使用 `from src.orchestration_engine import *` 时，哪些名字会被导入。
它也是一个很好的模块 API 目录，告诉使用者这个包对外提供了哪些核心工具。
"""
from .bootstrap import initialize
from .base_orchestrator import BaseOrchestrator
from .agent_registry import (
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
from .runtime_context import RuntimeContext
from .langgraph_runtime import LangGraphRuntime, LangGraphExecutable

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
    "initialize",
]
