import pytest
from src.model_provider.contracts import (
    InMemoryModelProviderClient,
    ModelRequest,
    ModelMessage,
    ModelResponse
)
from src.model_provider import ModelRouter

def test_mp_01_invoke_with_messages():
    """测试项 MP-01: 模拟客户端常规推理"""
    router = ModelRouter(clients={"test-model": InMemoryModelProviderClient()})
    
    request = ModelRequest(
        messages=(
            ModelMessage(role="system", content="You are a helpful assistant."),
            ModelMessage(role="user", content="Hello, how are you?"),
            ModelMessage(role="user", content="What is the weather today?")
        ),
        model_name="test-model"
    )
    
    response = router.completion(request)
    
    assert isinstance(response, ModelResponse)
    # 模拟客户端应该回显最后一条消息的内容
    assert response.content == "What is the weather today?"
    assert response.provider_id == "default"
    assert response.model_name == "test-model"
    assert response.finish_reason == "stop"

def test_mp_02_invoke_with_empty_messages():
    """测试项 MP-02: 模拟客户端空消息推理"""
    router = ModelRouter(clients={"default": InMemoryModelProviderClient()})
    
    request = ModelRequest(
        messages=(),
        model_name="default",
    )
    
    response = router.completion(request)
    
    assert isinstance(response, ModelResponse)
    assert response.content == ""
    assert response.provider_id == "default"
    assert response.model_name == "default"
