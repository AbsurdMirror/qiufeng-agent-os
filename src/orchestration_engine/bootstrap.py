from src.orchestration_engine.registry.agent_registry import AgentRegistry, AgentSpec, InMemoryAgentRegistry
from src.domain.capabilities import CapabilityDescription, CapabilityRequest, CapabilityResult
from src.orchestration_engine.contracts import CapabilityHub, NullCapabilityHub
from src.orchestration_engine.exports import OrchestrationEngineExports
from src.orchestration_engine.runtime.langgraph_runtime import LangGraphRuntime
from src.storage_memory.exports import StorageMemoryExports
from src.orchestration_engine.context.state_context_manager import StateContextManager
from src.observability_hub.exports import ObservabilityHubExports
from src.model_provider.contracts import ModelProviderClient


def initialize(
    capability_hub: CapabilityHub | None = None,
    storage_memory: StorageMemoryExports | None = None,
    observability: ObservabilityHubExports | None = None,
    model_provider: ModelProviderClient | None = None,
) -> OrchestrationEngineExports:
    """
    编排引擎层 (Orchestration Engine) 的初始化引导函数。
    
    该函数负责组装编排引擎的核心组件，包括：
    1. Agent 注册中心 (AgentRegistry)：存储和查询 Agent 规格。
    2. 运行时环境 (LangGraphRuntime)：支持基于图的编排执行。
    3. 能力中心 (CapabilityHub)：统一管理模型和工具的调用。
    4. 上下文管理器 (StateContextManager)：管理运行时的状态和记忆。

    Args:
        capability_hub: 可选的能力中心实现，若为空则使用 NullCapabilityHub。
        storage_memory: 可选的存储导出接口，用于状态持久化。
        observability: 可选的观测中心接口。
        model_provider: 可选的模型提供商客户端。

    Returns:
        OrchestrationEngineExports: 包含编排引擎所有对外暴露能力的导出对象。
    """
    registry = InMemoryAgentRegistry()
    langgraph_runtime = LangGraphRuntime()
    resolved_capability_hub = capability_hub or NullCapabilityHub()
    
    context_manager = None
    if storage_memory and model_provider:
        context_manager = StateContextManager(storage_memory, model_provider)

    return OrchestrationEngineExports(
        layer="orchestration_engine",
        status="initialized",
        agent_registry=registry,
        langgraph_runtime=langgraph_runtime,
        capability_hub=resolved_capability_hub,
        # 通过 lambda 延迟绑定内部私有辅助函数
        register_agent=lambda spec: _register_agent(registry=registry, spec=spec),
        query_agent=lambda agent_id, tenant_id, version=None: _query_agent(
            registry=registry,
            agent_id=agent_id,
            tenant_id=tenant_id,
            version=version,
        ),
        list_capabilities=lambda: _list_capabilities(capability_hub=resolved_capability_hub),
        get_capability=lambda capability_id: _get_capability(
            capability_hub=resolved_capability_hub,
            capability_id=capability_id,
        ),
        invoke_capability=lambda request: _invoke_capability(
            capability_hub=resolved_capability_hub,
            request=request,
        ),
        context_manager=context_manager,
    )


def _register_agent(registry: AgentRegistry, spec: AgentSpec) -> AgentSpec:
    """包装代理：向注册中心注册 Agent 规格"""
    return registry.register(spec)


def _query_agent(
    registry: AgentRegistry,
    agent_id: str,
    tenant_id: str,
    version: str | None = None,
) -> AgentSpec | None:
    """包装代理：从注册中心查询 Agent 规格"""
    return registry.get(agent_id=agent_id, tenant_id=tenant_id, version=version)


def _list_capabilities(capability_hub: CapabilityHub) -> tuple[CapabilityDescription, ...]:
    """包装代理：列出编排层当前可访问的能力描述"""
    return capability_hub.list_capabilities()


def _get_capability(
    capability_hub: CapabilityHub,
    capability_id: str,
) -> CapabilityDescription | None:
    """包装代理：按能力 ID 获取能力描述"""
    return capability_hub.get_capability(capability_id)


async def _invoke_capability(
    capability_hub: CapabilityHub,
    request: CapabilityRequest,
) -> CapabilityResult:
    """包装代理：通过统一请求对象调用能力"""
    return await capability_hub.invoke(request)
