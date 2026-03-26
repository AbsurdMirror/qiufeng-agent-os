import pytest
from src.orchestration_engine.agent_registry import (
    InMemoryAgentRegistry,
    AgentSpec,
    AgentIdentity,
    AgentOrchestrator,
    AgentCapabilityMap
)

@pytest.fixture
def registry():
    return InMemoryAgentRegistry()

def create_valid_spec(agent_id="agent_1", version="v1.0", tenant_id="tenant_A") -> AgentSpec:
    return AgentSpec(
        identity=AgentIdentity(agent_id=agent_id, version=version, tenant_id=tenant_id),
        metadata={"desc": "test agent"},
        orchestrator=AgentOrchestrator(engine_type="langgraph", entrypoint="my_module.run"),
        capability_map=AgentCapabilityMap(model_ids=("model_1",), skill_ids=("skill_1",)),
        config={}
    )

def test_oe_01_register_valid_agent(registry):
    """测试项 OE-01: 成功注册合法的 Agent"""
    spec = create_valid_spec()
    result = registry.register(spec)
    
    assert result == spec
    
    fetched = registry.get("agent_1", "tenant_A")
    assert fetched is not None
    assert fetched.identity.agent_id == "agent_1"
    
    all_agents = registry.list_all()
    assert len(all_agents) == 1

def test_oe_02_register_empty_fields(registry):
    """测试项 OE-02: 注册校验：字段为空"""
    # 测试空 agent_id
    invalid_spec = create_valid_spec(agent_id="")
    with pytest.raises(ValueError, match="invalid_agent_id"):
        registry.register(invalid_spec)
        
    # 测试空 version
    invalid_spec_version = create_valid_spec(version="  ")
    with pytest.raises(ValueError, match="invalid_version"):
        registry.register(invalid_spec_version)

def test_oe_03_get_agent_by_version(registry):
    """测试项 OE-03: 指定版本号获取 Agent"""
    spec_v1 = create_valid_spec(version="v1.0")
    spec_v2 = create_valid_spec(version="v2.0")
    
    registry.register(spec_v1)
    registry.register(spec_v2)
    
    fetched = registry.get("agent_1", "tenant_A", version="v1.0")
    assert fetched is not None
    assert fetched.identity.version == "v1.0"

def test_oe_04_get_latest_agent_without_version(registry):
    """测试项 OE-04: 不指定版本号获取最新 Agent"""
    spec_v1 = create_valid_spec(version="v1.0")
    spec_v2 = create_valid_spec(version="v2.0")
    spec_v1_5 = create_valid_spec(version="v1.5")
    
    registry.register(spec_v1)
    registry.register(spec_v2)
    registry.register(spec_v1_5)
    
    fetched = registry.get("agent_1", "tenant_A", version=None)
    assert fetched is not None
    # 按照字典序降序，v2.0 是最大的
    assert fetched.identity.version == "v2.0"

def test_oe_05_list_by_tenant(registry):
    """测试项 OE-05: 按租户列表查询"""
    registry.register(create_valid_spec(agent_id="a1", tenant_id="tenant_A"))
    registry.register(create_valid_spec(agent_id="a2", tenant_id="tenant_A"))
    registry.register(create_valid_spec(agent_id="a3", tenant_id="tenant_B"))
    
    tenant_a_agents = registry.list_by_tenant("tenant_A")
    assert len(tenant_a_agents) == 2
    for agent in tenant_a_agents:
        assert agent.identity.tenant_id == "tenant_A"
