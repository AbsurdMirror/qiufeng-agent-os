from src.model_provider import (
    MiniMaxModelProviderClient,
    ModelMessage,
    ModelRequest,
    build_litellm_completion_payload,
    build_model_response,
    initialize,
    LiteLLMRuntimeState,
)


def test_mp_03_litellm_payload_mapping_keeps_standard_fields():
    """测试项 MP-03: LiteLLM 请求映射保持统一字段对齐"""
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

    payload = build_litellm_completion_payload(
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
    request = ModelRequest(
        messages=(ModelMessage(role="user", content="hi"),),
        model_name="abab6.5s-chat",
    )
    response = build_model_response(
        {
            "model": "abab6.5s-chat",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": "你好，我是 MiniMax。",
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 7,
                "total_tokens": 19,
            },
        },
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
    monkeypatch.setattr("src.model_provider.providers.litellm_adapter._has_dependency", lambda name: False)
    monkeypatch.setattr(
        "src.model_provider.providers.litellm_adapter._read_dependency_version",
        lambda name: None,
    )

    client = MiniMaxModelProviderClient(api_key="secret", model_name="abab6.5s-chat")
    raw = client.completion({"model": "abab6.5s-chat", "messages": ()})

    assert raw["status"] == "degraded"
    assert raw["reason"] == "litellm_dependency_missing"
    assert raw["runtime"]["litellm_installed"] is False


def test_mp_06_minimax_client_returns_degraded_response_when_runtime_unavailable(monkeypatch):
    """测试项 MP-06: MiniMax 客户端在无依赖环境下返回标准降级结果"""
    monkeypatch.setattr("src.model_provider.providers.litellm_adapter._has_dependency", lambda name: False)
    monkeypatch.setattr(
        "src.model_provider.providers.litellm_adapter._read_dependency_version",
        lambda name: None,
    )
    client = MiniMaxModelProviderClient(api_key="secret", model_name="abab6.5s-chat")

    raw = client.completion({"model": "abab6.5s-chat", "messages": ()})

    assert raw["status"] == "degraded"
    assert raw["reason"] == "litellm_dependency_missing"


def test_mp_07_minimax_client_uses_litellm_mapping_when_runtime_ready(monkeypatch):
    """测试项 MP-07: MiniMax 客户端在可用时通过 LiteLLM 适配调用"""
    captured_payload: dict[str, object] = {}

    def fake_completion(**kwargs: object) -> dict[str, object]:
        captured_payload.update(kwargs)
        return {
            "model": kwargs["model"],
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": "MiniMax 调用成功"},
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 4,
                "total_tokens": 14,
            },
        }

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
    response = build_model_response(
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

        def completion(self, payload: dict[str, object]) -> dict[str, object]:
            captured.update(payload)
            return {
                "model": str(payload.get("model")),
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "ok"},
                    }
                ],
            }

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
