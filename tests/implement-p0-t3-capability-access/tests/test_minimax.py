import pytest

from src.model_provider.contracts import ModelRequest
from src.model_provider.minimax import is_minimax_request, MiniMaxModelProviderClient


def test_mm_01_heuristic_routing():
    """MM-01: 启发式请求判定"""
    
    # 命中 provider
    req1 = ModelRequest(messages=(), metadata={"provider": "minimax"})
    assert is_minimax_request(req1) is True
    
    # 命中 model_tag
    req2 = ModelRequest(messages=(), model_tag="model.minimax.chat")
    assert is_minimax_request(req2) is True
    
    # 命中 model_name
    req3 = ModelRequest(messages=(), model_name="abab6.5s-chat")
    assert is_minimax_request(req3) is True
    
    req4 = ModelRequest(messages=(), model_name="minimax/some-model")
    assert is_minimax_request(req4) is True
    
    # 未命中
    req5 = ModelRequest(messages=(), model_name="gpt-4")
    assert is_minimax_request(req5) is False


def test_mm_02_runtime_probe_missing_key(monkeypatch):
    """MM-02: 环境探测无 Key 降级"""
    monkeypatch.delenv("QF_MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    
    client = MiniMaxModelProviderClient()
    state = client.probe_runtime()
    
    assert state.available is False
    # 这里可能是 litellm 缺失，也可能是 key 缺失，由于测试环境不确定，只断言 degraded
    assert state.status == "degraded"


def test_mm_03_degraded_invocation(monkeypatch):
    """MM-03: 优雅降级调用"""
    # 强制让探针返回失败状态
    monkeypatch.setattr(
        "src.model_provider.minimax.probe_minimax_runtime",
        lambda **kw: type("MockState", (), {"available": False, "status": "degraded", "reason": "mock_reason", "to_dict": lambda self: {}})()
    )
    
    client = MiniMaxModelProviderClient()
    res = client.invoke(ModelRequest(messages=()))
    
    # 应该返回标准化错误响应而不是抛出异常
    assert res.finish_reason == "error"
    assert res.raw["status"] == "degraded"
    assert res.raw["reason"] == "mock_reason"
