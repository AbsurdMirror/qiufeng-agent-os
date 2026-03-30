from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from src.orchestration_engine.agent_registry import AgentRegistry, AgentSpec
from src.orchestration_engine.contracts import (
    CapabilityDescription,
    CapabilityHub,
    CapabilityRequest,
    CapabilityResult,
)
from src.orchestration_engine.langgraph_runtime import LangGraphRuntime


@dataclass(frozen=True)
class OrchestrationEngineExports:
    """
    编排引擎层 (Orchestration Engine) 的强类型导出对象 (数据类，不可变)。

    设计意图：
    将编排引擎层初始化后所有对外暴露的实例和快捷方法打包在一起。
    这样其他层（如 App 层）在调用时，IDE 能够提供准确的代码提示和跳转，
    避免了使用普通字典 dict[str, Any] 带来的类型丢失问题。

    初学者提示：
    `Callable[[参数类型], 返回类型]` 是用来注解函数的类型。
    例如 `Callable[[AgentSpec], AgentSpec]` 表示这是一个函数，它接收一个 AgentSpec 类型的参数，并返回一个 AgentSpec 类型的结果。
    `Awaitable` 表示这是一个异步方法（需要用 await 调用）。
    """
    # 当前所属的层级名称，例如 "orchestration_engine"
    layer: str
    # 模块的当前状态，例如 "initialized"
    status: str
    
    # 核心实例的引用
    # Agent 注册中心，负责存储和查询智能体配置
    agent_registry: AgentRegistry
    # LangGraph 运行时，具体的编排引擎实现
    langgraph_runtime: LangGraphRuntime
    # 注入的能力中心，用于访问外部工具或模型
    capability_hub: CapabilityHub
    
    # 快捷方法（代理函数），方便外部直接调用而无需层层访问实例属性
    # 注册一个 Agent 规格
    register_agent: Callable[[AgentSpec], AgentSpec]
    # 查询一个指定的 Agent 规格
    query_agent: Callable[[str, str, str | None], AgentSpec | None]
    
    # 暴露能力中心的相关方法
    # 列出所有可用的能力
    list_capabilities: Callable[[], tuple[CapabilityDescription, ...]]
    # 根据 ID 获取某个能力的描述
    get_capability: Callable[[str], CapabilityDescription | None]
    # 异步执行某个能力（如调用模型或工具）
    invoke_capability: Callable[[CapabilityRequest], Awaitable[CapabilityResult]]

    # 上下文管理器，负责状态读取与持久化
    context_manager: Any
