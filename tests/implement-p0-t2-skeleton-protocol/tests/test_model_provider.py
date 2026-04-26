import pytest
from unittest.mock import MagicMock
import litellm
from src.domain.models import ModelMessage, ModelRequest, ModelResponse
from src.model_provider import ModelRouter


def _mock_litellm_response(*, model: str, content: str, finish_reason: str = "stop") -> litellm.ModelResponse:
    response = MagicMock(spec=litellm.ModelResponse)
    choice = MagicMock()
    choice.finish_reason = finish_reason
    choice.message = MagicMock()
    choice.message.content = content
    choice.message.role = "assistant"
    choice.message.tool_calls = None
    choice.message.function_call = None
    response.choices = [choice]
    response.usage = None
    response.model = model
    return response

def test_mp_01_invoke_with_messages():
    """测试项 MP-01: 模拟客户端常规推理"""
    class _Client:
        provider_id = "default"

        def completion(self, payload):
            messages = payload.get("messages") or ()
            last_content = ""
            if messages:
                last_content = str(messages[-1].get("content") or "")
            return _mock_litellm_response(model=str(payload.get("model")), content=last_content)

    router = ModelRouter(clients={"default": _Client()})
    
    request = ModelRequest(
        messages=(
            ModelMessage(role="system", content="You are a helpful assistant."),
            ModelMessage(role="user", content="Hello, how are you?"),
            ModelMessage(role="user", content="What is the weather today?")
        ),
        model_name="default"
    )
    
    response = router.completion(request)
    
    assert isinstance(response, ModelResponse)
    # 模拟客户端应该回显最后一条消息的内容
    assert response.content == "What is the weather today?"
    assert response.provider_id == "default"
    assert response.model_name == "default"
    assert response.finish_reason == "stop"

def test_mp_02_invoke_with_empty_messages():
    """测试项 MP-02: 模拟客户端空消息推理"""
    class _Client:
        provider_id = "default"

        def completion(self, payload):
            return ModelResponse(
                success=True,
                model_name=str(payload.get("model")),
                content="",
                finish_reason="stop",
                provider_id=self.provider_id,
            )

    router = ModelRouter(clients={"default": _Client()})
    
    request = ModelRequest(
        messages=(),
        model_name="default",
    )
    
    response = router.completion(request)
    
    assert isinstance(response, ModelResponse)
    assert response.content == ""
    assert response.provider_id == "default"
    assert response.model_name == "default"
