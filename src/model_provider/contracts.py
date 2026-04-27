from collections.abc import Mapping
from typing import Protocol, Union

from src.domain.models import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
)
import litellm

LiteLLMRawResponse = Union["litellm.ModelResponse", "litellm.CustomStreamWrapper", ModelResponse]


class ModelProviderClient(Protocol):
    """
    对外模型提供商客户端协议 (Outer Interface)。
    输入为 ModelRequest，输出为 ModelResponse。
    适用于 Router 和独立的模拟客户端。
    """
    provider_id: str

    def completion(self, request: ModelRequest) -> ModelResponse:
        raise NotImplementedError


class RawModelProviderClient(Protocol):
    """
    对内模型提供商客户端协议 (Inner Interface)。
    输入为 Mapping[str, object]，输出为 LiteLLM 兼容的原始响应。
    适用于具体模型的适配器实现（如 MiniMax）。
    """
    provider_id: str

    def completion(self, payload: Mapping[str, object]) -> LiteLLMRawResponse:
        raise NotImplementedError


class InMemoryModelProviderClient:
    """
    内存级模拟模型客户端 (Mock Provider) - 对外版本。
    
    接口输入为 ModelRequest，输出为 ModelResponse。
    """
    provider_id = "default"

    def completion(self, request: ModelRequest) -> ModelResponse:
        """
        简单地将用户输入的最后一条消息作为模型回复返回。
        """
        last_content = ""
        if request.messages:
            last_message = request.messages[-1]
            last_content = last_message.content or ""
        
        return ModelResponse(
            success=True,
            model_name=request.model_name or "mock-model",
            content=last_content,
            finish_reason="stop",
            provider_id=self.provider_id,
            message=ModelMessage(role="assistant", content=last_content),
            raw={
                "model": request.model_name or "mock-model",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": last_content},
                    }
                ],
            }
        )
