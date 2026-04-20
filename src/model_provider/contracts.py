from typing import Any, Mapping, Protocol
from src.domain.models import (
    ModelRequest,
    ModelResponse,
)


class ModelProviderClient(Protocol):
    """
    模型提供商客户端协议 (Duck Typing Interface)。
    所有具体的模型服务商接入实现都必须遵循此同步调用契约。
    """
    provider_id: str

    def completion(self, request: ModelRequest) -> ModelResponse:
        raise NotImplementedError


class InMemoryModelProviderClient:
    """
    内存级模拟模型客户端 (Mock Provider)。
    
    主要用于 P0 T2 阶段打通链路和单元测试，它会简单地将用户输入的最后一条消息作为模型回复返回。
    """
    provider_id = "default"

    def completion(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """
        生成 LiteLLM 兼容的 mock 原始响应。
        该方法用于 Router 主链路的 completion(payload)->raw 调用约定。
        """
        raw_messages = payload.get("messages")
        last_content = ""
        if isinstance(raw_messages, tuple) and raw_messages:
            last_item = raw_messages[-1]
            if isinstance(last_item, dict):
                last_content = str(last_item.get("content", ""))
        return {
            "model": str(payload.get("model") or "mock-model"),
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": last_content},
                }
            ],
        }
