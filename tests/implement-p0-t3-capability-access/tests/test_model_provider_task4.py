from unittest.mock import MagicMock
import litellm
from src.model_provider import (
    MiniMaxModelProviderClient,
    ModelMessage,
    ModelRequest,
    initialize,
    LiteLLMRuntimeState,
)
from src.model_provider.providers.litellm_adapter import LiteLLMAdapter


def _mock_litellm_response(
    *,
    model: str,
    content: str,
    finish_reason: str = "stop",
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
) -> litellm.ModelResponse:
    response = MagicMock(spec=litellm.ModelResponse)
    choice = MagicMock()
    choice.finish_reason = finish_reason
    choice.message = MagicMock()
    choice.message.content = content
    choice.message.role = "assistant"
    choice.message.tool_calls = None
    choice.message.function_call = None
    response.choices = [choice]
    if prompt_tokens is None and completion_tokens is None and total_tokens is None:
        response.usage = None
    else:
        usage = MagicMock()
        usage.prompt_tokens = prompt_tokens
        usage.completion_tokens = completion_tokens
        usage.total_tokens = total_tokens
        response.usage = usage
    response.model = model
    return response


def test_mp_03_litellm_request_payload_mapping_aligned():
    """测试项 MP-03: LiteLLM 请求映射保持统一字段对齐"""
    adapter = LiteLLMAdapter()
    request = ModelRequest(
        messages=(
            ModelMessage(role="system", content="你是助手"),
            ModelMessage(role="user", content="介绍一下你自己"),
        ),
        model_name="abab6.5s-chat",
        temperature=0.4,
        top_p=0.8,
        max_tokens=512,
        metadata={
            "trace_id": "trace-1",
            "litellm_kwargs": {"timeout": 30},
        },
    )

    payload = adapter.build_litellm_completion_payload(
        request,
        api_key="secret",
        base_url="https://api.minimax.chat/v1",
    )

    assert payload["model"] == "abab6.5s-chat"
    assert payload["messages"] == (
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "介绍一下你自己"},
    )
    assert payload["temperature"] == 0.4
    assert payload["top_p"] == 0.8
    assert payload["max_tokens"] == 512
    assert payload["api_key"] == "secret"
    assert payload["base_url"] == "https://api.minimax.chat/v1"
    assert payload["metadata"] == {"trace_id": "trace-1"}
    assert payload["timeout"] == 30


def test_mp_04_litellm_response_mapping_normalizes_usage_and_content():
    """测试项 MP-04: LiteLLM 响应映射回收统一 ModelResponse"""
    adapter = LiteLLMAdapter()
    request = ModelRequest(
        messages=(ModelMessage(role="user", content="hi"),),
        model_name="abab6.5s-chat",
    )
    response = adapter.build_model_response(
        _mock_litellm_response(
            model="abab6.5s-chat",
            content="你好，我是 MiniMax。",
            finish_reason="stop",
            prompt_tokens=12,
            completion_tokens=7,
            total_tokens=19,
        ),
        request=request,
        output_schema=None,
        fallback_model_name="abab6.5s-chat",
        provider_id="minimax",
    )

    assert response.model_name == "abab6.5s-chat"
    assert response.content == "你好，我是 MiniMax。"
    assert response.finish_reason == "stop"
    assert response.provider_id == "minimax"
    assert response.usage is not None
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 7
    assert response.usage.total_tokens == 19


def test_mp_05_minimax_completion_degrades_without_litellm(monkeypatch):
    """测试项 MP-05: 缺失 LiteLLM 依赖时返回明确降级状态"""
    monkeypatch.setattr(
        "src.model_provider.providers.litellm_adapter.find_spec",
        lambda name: None,
    )
    client = MiniMaxModelProviderClient(api_key="secret", model_name="abab6.5s-chat")
    response = client.completion({"model": "abab6.5s-chat", "messages": ()})

    assert response.success is False
    assert response.raw["status"] == "degraded"
    assert response.raw["reason"] == "litellm_dependency_missing"
    assert response.raw["runtime"]["litellm_installed"] is False


def test_mp_06_minimax_client_returns_degraded_response_when_runtime_unavailable(monkeypatch):
    """测试项 MP-06: MiniMax 客户端在无依赖环境下返回标准降级结果"""
    monkeypatch.setattr(
        "src.model_provider.providers.litellm_adapter.find_spec",
        lambda name: None,
    )
    client = MiniMaxModelProviderClient(api_key="secret", model_name="abab6.5s-chat")

    response = client.completion({"model": "abab6.5s-chat", "messages": ()})

    assert response.success is False
    assert response.raw["status"] == "degraded"
    assert response.raw["reason"] == "litellm_dependency_missing"


def test_mp_07_minimax_client_uses_litellm_mapping_when_runtime_ready(monkeypatch):
    """测试项 MP-07: MiniMax 客户端在可用时通过 LiteLLM 适配调用"""
    captured_payload: dict[str, object] = {}

    def fake_completion(**kwargs: object) -> litellm.ModelResponse:
        captured_payload.update(kwargs)
        return _mock_litellm_response(
            model=str(kwargs["model"]),
            content="MiniMax 调用成功",
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=4,
            total_tokens=14,
        )

    monkeypatch.setattr(
        "src.model_provider.providers.minimax.probe_litellm_runtime",
        lambda: LiteLLMRuntimeState(
            litellm_installed=True,
            available=True,
            status="ready",
            reason=None,
            litellm_version="1.63.0",
            metadata={"provider": "litellm"},
        ),
    )
    monkeypatch.setattr("src.model_provider.providers.minimax.litellm.completion", fake_completion)
    client = MiniMaxModelProviderClient(
        api_key="secret",
        model_name="abab6.5s-chat",
    )

    adapter = LiteLLMAdapter()
    raw = client.completion(
        {
            "model": "abab6.5s-chat",
            "messages": (
                {"role": "system", "content": "s1"},
                {"role": "system", "content": "s2"},
                {"role": "user", "content": "u"},
            ),
        }
    )
    response = adapter.build_model_response(
        raw,
        request=ModelRequest(messages=(ModelMessage(role="user", content="u"),), model_name="abab6.5s-chat"),
        output_schema=None,
        fallback_model_name="abab6.5s-chat",
        provider_id=client.provider_id,
    )

    assert captured_payload["model"] == "abab6.5s-chat"
    assert captured_payload["api_key"] == "secret"
    assert captured_payload["messages"] == [
        {"role": "system", "content": "s1\n\ns2"},
        {"role": "user", "content": "u"},
    ]
    assert response.content == "MiniMax 调用成功"
    assert response.provider_id == "minimax"


def test_mp_08_initialize_routes_minimax_requests_to_specialized_client(monkeypatch):
    """测试项 MP-08: 初始化后的模型层可添加并路由到指定模型客户端"""
    captured: dict[str, object] = {}

    class _StubClient:
        provider_id = "minimax"

        def completion(self, payload: dict[str, object]) -> litellm.ModelResponse:
            captured.update(payload)
            return _mock_litellm_response(model=str(payload.get("model")), content="ok")

    exports = initialize()
    router = exports.client
    assert hasattr(router, "add_client")
    router.add_client("minimax", _StubClient())

    response = exports.invoke_sync(
        ModelRequest(
            messages=(ModelMessage(role="user", content="你好"),),
            model_name="minimax",
        )
    )

    assert response.provider_id == "minimax"
    assert captured["model"] == "minimax"