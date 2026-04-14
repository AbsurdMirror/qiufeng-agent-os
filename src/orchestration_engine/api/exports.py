from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from src.orchestration_engine.registry.agent_registry import AgentRegistry, AgentSpec
from src.orchestration_engine.contracts import (
    CapabilityDescription,
    CapabilityHub,
    CapabilityRequest,
    CapabilityResult,
)
from src.orchestration_engine.runtime.langgraph_runtime import LangGraphRuntime


@dataclass(frozen=True)
class OrchestrationEngineExports:
    """
    编排引擎层 (Orchestration Engine) 的强类型导出对象 (数据类，不可变)。

    设计意图：
    将编排引擎层初始化后所有对外暴露的实例和快捷方法打包在一起。
    这样其他层（如 App 层）在调用时，IDE 能够提供准确的代码提示和跳转，
    避免了使用普通字典 dict[str, Any] 带来的类型丢失问题。
    """
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
