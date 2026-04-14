from src.model_provider import (
    MiniMaxModelProviderClient,
    ModelMessage,
    ModelRequest,
    build_litellm_completion_payload,
    initialize,
    normalize_litellm_response,
    probe_minimax_runtime,
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
        provider="minimax",
        api_key="secret",
        base_url="https://api.minimax.chat/v1",
    )

    assert payload["model"] == "minimax/abab6.5s-chat"
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
    response = normalize_litellm_response(
        {
            "model": "minimax/abab6.5s-chat",
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
        fallback_model_name="minimax/abab6.5s-chat",
        provider_id="minimax",
    )

    assert response.model_name == "minimax/abab6.5s-chat"
    assert response.content == "你好，我是 MiniMax。"
    assert response.finish_reason == "stop"
    assert response.provider_id == "minimax"
    assert response.usage is not None
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 7
    assert response.usage.total_tokens == 19


def test_mp_05_probe_minimax_runtime_degrades_without_litellm(monkeypatch):
    """测试项 MP-05: 缺失 LiteLLM 依赖时返回明确降级状态"""
    monkeypatch.setattr("src.model_provider.litellm_adapter._has_dependency", lambda name: False)
    monkeypatch.setattr(
        "src.model_provider.litellm_adapter._read_dependency_version",
        lambda name: None,
    )

    state = probe_minimax_runtime(api_key="secret", model_name="abab6.5s-chat")

    assert state.available is False
    assert state.status == "degraded"
    assert state.reason == "litellm_dependency_missing"
    assert state.api_key_configured is True
    assert state.to_dict()["litellm_installed"] is False


def test_mp_06_minimax_client_returns_degraded_response_when_runtime_unavailable(monkeypatch):
    """测试项 MP-06: MiniMax 客户端在无依赖环境下返回标准降级结果"""
    monkeypatch.setattr("src.model_provider.litellm_adapter._has_dependency", lambda name: False)
    monkeypatch.setattr(
        "src.model_provider.litellm_adapter._read_dependency_version",
        lambda name: None,
    )
    client = MiniMaxModelProviderClient(api_key="secret", model_name="abab6.5s-chat")

    response = client.invoke(
        ModelRequest(
            messages=(ModelMessage(role="user", content="你好"),),
            model_name="minimax/abab6.5s-chat",
        )
    )

    assert response.model_name == "minimax/abab6.5s-chat"
    assert response.content == ""
    assert response.finish_reason == "error"
    assert response.provider_id == "minimax"
    assert response.raw["status"] == "degraded"
    assert response.raw["reason"] == "litellm_dependency_missing"


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

    monkeypatch.setattr("src.model_provider.litellm_adapter._has_dependency", lambda name: True)
    monkeypatch.setattr(
        "src.model_provider.litellm_adapter._read_dependency_version",
        lambda name: "1.63.0",
    )
    client = MiniMaxModelProviderClient(
        api_key="secret",
        model_name="abab6.5s-chat",
        completion_callable=fake_completion,
    )

    response = client.invoke(
        ModelRequest(
            messages=(ModelMessage(role="user", content="请介绍一下 MiniMax"),),
            model_name="abab6.5s-chat",
            metadata={"trace_id": "trace-7"},
        )
    )

    assert captured_payload["model"] == "minimax/abab6.5s-chat"
    assert captured_payload["metadata"] == {"trace_id": "trace-7"}
    assert response.content == "MiniMax 调用成功"
    assert response.provider_id == "minimax"
    assert response.raw["runtime"]["status"] == "ready"


def test_mp_08_initialize_routes_minimax_requests_to_specialized_client(monkeypatch):
    """测试项 MP-08: 初始化后的模型层可识别 MiniMax 请求并进入降级分支"""
    monkeypatch.setattr("src.model_provider.litellm_adapter._has_dependency", lambda name: False)
    monkeypatch.setattr(
        "src.model_provider.litellm_adapter._read_dependency_version",
        lambda name: None,
    )
    exports = initialize()

    response = exports.invoke_sync(
        ModelRequest(
            messages=(ModelMessage(role="user", content="你好"),),
            model_name="minimax",
        )
    )

    assert response.provider_id == "minimax"
    assert response.raw["status"] == "degraded"
