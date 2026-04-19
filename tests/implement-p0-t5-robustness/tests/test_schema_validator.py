from pydantic import BaseModel

from src.model_provider import ModelMessage, ModelRequest, ModelRouter
from src.model_provider.contracts import ModelResponseParseConfig


class _DemoSchema(BaseModel):
    title: str
    score: int


def test_mp_t5_01_router_retries_and_strips_json_code_fence():
    """测试项 MP-T5-01: 通过 Router 入口验证 schema 解析失败后重试，且支持剥离 ```json 代码块"""
    calls = {"n": 0, "messages": []}

    class _Client:
        provider_id = "stub"

        def completion(self, payload):
            calls["n"] += 1
            calls["messages"].append(payload.get("messages"))
            if calls["n"] == 1:
                return {
                    "model": payload.get("model"),
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": '```json\n{"title":"x"}\n```'},
                        }
                    ],
                }
            return {
                "model": payload.get("model"),
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '```json\n{"title":"ok","score":1}\n```'},
                    }
                ],
            }

    router = ModelRouter(clients={"demo": _Client()})
    response = router.completion(
        ModelRequest(
            messages=(ModelMessage(role="user", content="hi"),),
            model_name="demo",
            response_parse=ModelResponseParseConfig(output_schema=_DemoSchema, schema_max_retries=1),
        )
    )

    assert calls["n"] == 2
    assert response.success is True
    assert response.parsed.title == "ok"
    assert response.parsed.score == 1
    assert any(
        isinstance(batch, tuple)
        and any(
            isinstance(item, dict)
            and item.get("role") == "user"
            and "你的上一次输出在解析阶段出错" in str(item.get("content", ""))
            for item in batch
        )
        for batch in calls["messages"]
    )


def test_mp_t5_02_router_exhausts_retries_and_returns_error_response():
    """测试项 MP-T5-02: 通过 Router 入口验证 max_retries 语义为“首次 + 重试次数”"""
    calls = {"n": 0}

    class _Client:
        provider_id = "stub"

        def completion(self, payload):
            calls["n"] += 1
            return {
                "model": payload.get("model"),
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"title":"x"}'},
                    }
                ],
            }

    router = ModelRouter(clients={"demo": _Client()})
    response = router.completion(
        ModelRequest(
            messages=(ModelMessage(role="user", content="hi"),),
            model_name="demo",
            response_parse=ModelResponseParseConfig(output_schema=_DemoSchema, schema_max_retries=2),
        )
    )

    assert calls["n"] == 3
    assert response.success is False
    assert response.finish_reason == "error"
    assert response.raw["retry_count"] == 2
