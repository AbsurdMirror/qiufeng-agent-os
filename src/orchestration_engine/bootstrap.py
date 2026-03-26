from src.orchestration_engine.agent_registry import AgentRegistry, AgentSpec, InMemoryAgentRegistry
from src.orchestration_engine.exports import OrchestrationEngineExports


def initialize() -> OrchestrationEngineExports:
    """
    编排引擎层 (Orchestration Engine) 的初始化引导函数。
    
    此函数会被 `src.app.bootstrap` 在应用启动时调用。它负责：
    初始化单例的内存注册中心，并暴露代理方法供其他模块注册和查询 Agent 规格。
    """
    # 实例化基于内存的注册中心
    registry = InMemoryAgentRegistry()
    return OrchestrationEngineExports(
        layer="orchestration_engine",
        status="initialized",
        agent_registry=registry,
        register_agent=lambda spec: _register_agent(registry=registry, spec=spec),
        query_agent=lambda agent_id, tenant_id, version=None: _query_agent(
            registry=registry,
            agent_id=agent_id,
            tenant_id=tenant_id,
            version=version,
        ),
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
