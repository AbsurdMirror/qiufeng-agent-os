from dataclasses import dataclass, field
from typing import Any, Literal

from src.domain.capabilities import CapabilityDescription, CapabilityRequest


@dataclass(frozen=True)
class ToolCallFunction:
    name: str | None
    arguments: str | None


@dataclass(frozen=True)
class ToolInvocation:
    id: str | None
    function: ToolCallFunction
    type: Literal["function"] = "function"

    def to_str(self) -> str:
        """将 ToolInvocation 转换为字符串表示"""
        import json
        json_dict = {
            "id": self.id,
            "type": self.type,
            "function": {
                "name": self.function.name,
                "arguments": self.function.arguments,
            },
        }
        return json.dumps(json_dict, ensure_ascii=False)


@dataclass(frozen=True)
class ModelMessage:
    """
    模型对话消息的标准结构。
    
    Attributes:
        role: 角色标识（如 "system", "user", "assistant"）。
        content: 消息内容载荷。
    """
    role: str
    content: str | None
    tool_calls: tuple[ToolInvocation, ...] = ()


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
    output_schema: Any | None = None
    max_retries: int = 3
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
    content: str | None
    success: bool = True
    finish_reason: str | None = None
    provider_id: str | None = None
    usage: ModelUsage | None = None
    parsed: Any = None
    tool_calls: tuple[CapabilityRequest, ...] = ()
    tool_invocations: tuple[ToolInvocation, ...] = ()
    repair_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
