import pytest
from unittest.mock import AsyncMock

from src.domain.capabilities import CapabilityDescription, CapabilityRequest, CapabilityResult
from src.skill_hub.core.capability_hub import RegisteredCapabilityHub
from src.model_provider.routing.router import ModelRouter
from src.domain.models import ModelMessage, ModelResponse


@pytest.fixture
def hub():
    return RegisteredCapabilityHub()


def test_ch_01_register_and_discovery(hub: RegisteredCapabilityHub):
    """CH-01: 能力注册与发现"""
    desc = CapabilityDescription(
        capability_id="test.mock.cap",
        domain="test",
        name="test_cap",
        description="A test capability",
        input_schema={},
        output_schema={},
        metadata={}
    )
    mock_handler = AsyncMock()
    
    hub.register_capability(desc, mock_handler)
    
    caps = hub.list_capabilities()
    assert len(caps) == 1
    assert caps[0].capability_id == "test.mock.cap"
    
    fetched = hub.get_capability("test.mock.cap")
    assert fetched is not None
    assert fetched.name == "test_cap"


@pytest.mark.anyio
async def test_ch_02_invoke_not_found(hub: RegisteredCapabilityHub):
    """CH-02: 调用不存在的能力"""
    req = CapabilityRequest(capability_id="not.exist.cap", payload={}, metadata={})
    res = await hub.invoke(req)
    
    assert res.success is False
    assert res.error_code == "capability_not_found"
    assert "not registered" in res.error_message


@pytest.mark.anyio
async def test_ch_03_invoke_success_with_metadata(hub: RegisteredCapabilityHub):
    """CH-03: 正常能力调用与元数据自动补充"""
    desc = CapabilityDescription(
        capability_id="test.mock.cap",
        domain="test_domain",
        name="test_cap",
        description="",
        input_schema={},
        output_schema={},
        metadata={}
    )
    
    async def mock_handler(req: CapabilityRequest) -> CapabilityResult:
        return CapabilityResult(
            capability_id=req.capability_id,
            success=True,
            output={"result": "ok"},
            metadata={"custom": "value"}
        )
        
    hub.register_capability(desc, mock_handler)
    
    req = CapabilityRequest(capability_id="test.mock.cap", payload={}, metadata={})
    res = await hub.invoke(req)
    
    assert res.success is True
    assert res.output["result"] == "ok"
    # 验证 domain 被自动补充到 metadata 中
    assert res.metadata["domain"] == "test_domain"
    assert res.metadata["custom"] == "value"


@pytest.mark.anyio
async def test_mr_01_02_build_model_request(hub: RegisteredCapabilityHub):
    """MR-01 & MR-02: payload 解析与验证（通过 Hub 的新机制）"""
    class _Client:
        provider_id = "stub"
        def completion(self, request):
            return ModelResponse(model_name="test", content="ok", success=True)
            
    router = ModelRouter(clients={"default": _Client()})
    hub.register_instance_capabilities(router)
    
    # 正常解析：messages 必须是 tuple[ModelMessage, ...]
    req1 = CapabilityRequest(
        capability_id="model.completion",
        payload={"request": {"messages": (ModelMessage(role="user", content="hello world"),)}},
        metadata={}
    )
    res1 = await hub.invoke(req1)
    assert res1.success is True
    
    # MR-02: 缺失必填字段 (model_name 在 router 层面是可选的，但 messages 是必填的)
    req2 = CapabilityRequest(
        capability_id="model.completion",
        payload={"request": {}},
        metadata={}
    )
    res2 = await hub.invoke(req2)
    assert res2.success is False
    assert "messages" in res2.error_message


@pytest.mark.anyio
async def test_mr_03_route_to_default_client(hub: RegisteredCapabilityHub):
    """MR-03: 路由到默认客户端 (default)"""
    class _Client:
        provider_id = "stub"
        def completion(self, request):
            return {
                "model": "default",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "from default"},
                        "finish_reason": "stop"
                    }
                ]
            }
            
    router = ModelRouter(clients={"default": _Client()})
    hub.register_instance_capabilities(router)
    
    req = CapabilityRequest(
        capability_id="model.completion",
        payload={"request": {"messages": (ModelMessage(role="user", content="hi"),)}},
        metadata={}
    )
    res = await hub.invoke(req)
    assert res.success is True
    assert res.output["result"]["content"] == "from default"


@pytest.mark.anyio
async def test_mr_04_forced_provider_routing(hub: RegisteredCapabilityHub):
    """MR-04: 模型能力路由可转发到 ModelProviderClient.completion"""
    calls = {"n": 0}
    
    class _Client:
        provider_id = "stub"
        def completion(self, request):
            calls["n"] += 1
            # request 是 dict
            assert request["metadata"]["trace_id"] == "trace-1"
            assert request["metadata"]["x"] == "y"
            return {
                "model": "demo",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "mock"},
                    }
                ],
            }
            
    router = ModelRouter(clients={"demo": _Client()})
    hub.register_instance_capabilities(router)
    
    req = CapabilityRequest(
        capability_id="model.completion",
        payload={"request": {
            "messages": (ModelMessage(role="user", content="hi"),),
            "model_name": "demo",
            "metadata": {"x": "y", "trace_id": "trace-1"},
        }},
        metadata={"trace_id": "trace-1"},
    )
    res = await hub.invoke(req)
    assert res.success is True
    assert res.output["result"]["content"] == "mock"
    assert calls["n"] == 1
