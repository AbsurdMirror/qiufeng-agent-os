import pytest
from unittest.mock import AsyncMock, Mock

from src.orchestration_engine.contracts import CapabilityDescription, CapabilityRequest, CapabilityResult
from src.skill_hub.core.capability_hub import RegisteredCapabilityHub, ModelCapabilityRouter
from src.model_provider.contracts import ModelRequest, ModelResponse


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


def test_mr_01_02_build_model_request():
    """MR-01 & MR-02: 兼容参数组装与空拦截"""
    from src.skill_hub.core.capability_hub import _build_model_request
    
    # 测试 prompt 兼容转换
    req1 = CapabilityRequest(
        capability_id="model.chat",
        payload={"prompt": "hello world"},
        metadata={}
    )
    model_req1, err1 = _build_model_request(request=req1, forced_model_tag=None, forced_provider=None)
    assert err1 is None
    assert len(model_req1.messages) == 1
    assert model_req1.messages[0].content == "hello world"
    assert model_req1.messages[0].role == "user"
    
    # 测试空拦截
    req2 = CapabilityRequest(
        capability_id="model.chat",
        payload={},
        metadata={}
    )
    model_req2, err2 = _build_model_request(request=req2, forced_model_tag=None, forced_provider=None)
    assert err2 is not None
    assert err2.success is False
    assert err2.error_code == "invalid_model_request"


def test_mr_03_build_model_result():
    """MR-03: 响应状态回收"""
    from src.skill_hub.core.capability_hub import _build_model_result
    
    req = CapabilityRequest(capability_id="model.chat", payload={}, metadata={})
    resp_error = ModelResponse(
        model_name="test",
        content="",
        finish_reason="error",
        provider_id="test",
        usage=None,
        raw={"reason": "rate_limit", "status": "degraded"}
    )
    
    res = _build_model_result(request=req, response=resp_error, fallback_provider=None)
    assert res.success is False
    assert res.error_code == "rate_limit"


@pytest.mark.anyio
async def test_mr_04_forced_provider_routing():
    """MR-04: 强制提供商路由 (MiniMax)"""
    mock_client = Mock()
    mock_client.invoke.return_value = ModelResponse(
        model_name="mock", content="mock", finish_reason="stop", provider_id="mock", usage=None, raw={}
    )
    router = ModelCapabilityRouter(mock_client)
    
    req = CapabilityRequest(
        capability_id="model.minimax.chat",
        payload={"prompt": "hi"},
        metadata={}
    )
    
    await router.invoke_minimax(req)
    
    # 验证传递给 client 的 request 包含了 forced provider
    called_req = mock_client.invoke.call_args[0][0]
    assert called_req.metadata["provider"] == "minimax"
    assert called_req.model_tag == "model.minimax.chat"
