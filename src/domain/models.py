from dataclasses import dataclass, field
from typing import Any

from src.domain.capabilities import CapabilityDescription, CapabilityRequest


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
class ModelResponseParseConfig:
    """
    模型响应解析配置：
    - output_schema: content 结构化解析目标 Schema；
    - schema_max_retries: content/tool_calls 解析失败时的最大重试次数。
    """
    output_schema: Any | None = None
    schema_max_retries: int = 0


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
    tools: tuple[CapabilityDescription, ...] = ()
    response_parse: "ModelResponseParseConfig" = field(default_factory=lambda: ModelResponseParseConfig())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelUsage:
    """模型推理的 Token 消耗统计"""
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    def to_dict(self) -> dict[str, int | None]:
        """将 Usage 转换为字典格式"""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


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
    success: bool = True
    finish_reason: str | None = None
    provider_id: str | None = None
    usage: ModelUsage | None = None
    parsed: Any = None
    tool_calls: tuple[CapabilityRequest, ...] = ()
    repair_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

