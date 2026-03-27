from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ModelMessage:
    """
    模型对话消息的标准结构。
    
    Attributes:
        role: 角色标识（如 "system", "user", "assistant"）。
        content: 消息内容载荷。
    """
    role: str
    content: str


@dataclass(frozen=True)
class ModelRequest:
    """
    模型推理请求的统一输入参数模型。
    
    设计意图：
    将各个供应商（如 OpenAI, Minimax）繁杂的特定参数统一抽象，
    供上层编排引擎以标准化的方式发起推理请求。
    """
    messages: tuple[ModelMessage, ...]
    model_name: str | None = None
    model_tag: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelUsage:
    """模型推理的 Token 消耗统计"""
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class ModelResponse:
    """
    模型推理结果的统一输出模型。
    
    Attributes:
        model_name: 实际提供服务的模型名称。
        content: 模型返回的文本结果。
        finish_reason: 推理停止的原因（如 "stop", "length"）。
        provider_id: 底层供应商标识（如 "openai", "in_memory"）。
        usage: 此次推理的 Token 消耗量。
        raw: 供应商返回的原始 JSON 数据，用于 Debug 和兜底。
    """
    model_name: str
    content: str
    finish_reason: str | None = None
    provider_id: str | None = None
    usage: ModelUsage | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class ModelProviderClient(Protocol):
    """
    模型提供商客户端协议 (Duck Typing Interface)。
    所有具体的模型服务商接入实现都必须遵循此同步调用契约。
    """
    def invoke(self, request: ModelRequest) -> ModelResponse:
        raise NotImplementedError


class InMemoryModelProviderClient:
    """
    内存级模拟模型客户端 (Mock Provider)。
    
    主要用于 P0 T2 阶段打通链路和单元测试，它会简单地将用户输入的最后一条消息作为模型回复返回。
    """
    def invoke(self, request: ModelRequest) -> ModelResponse:
        latest_message = request.messages[-1].content if request.messages else ""
        return ModelResponse(
            model_name=request.model_name or request.model_tag or "mock-model",
            content=latest_message,
            finish_reason="stop",
            provider_id="in_memory",
            usage=None,
            raw={},
        )

