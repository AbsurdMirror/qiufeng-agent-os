from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
import json
from typing import Literal, TypeAlias

from pydantic import BaseModel

from src.domain.capabilities import CapabilityDescription, CapabilityRequest
from src.domain.translators.model_interactions import ParsedToolCall


ModelMessageRole: TypeAlias = Literal["system", "user", "assistant", "tool"]
ModelOutputSchema: TypeAlias = type[BaseModel] | Mapping[str, object]


@dataclass(frozen=True)
class ToolCallFunction:
    name: str
    arguments: str


@dataclass(frozen=True)
class ToolInvocation:
    id: str | None
    function: ToolCallFunction
    type: Literal["function"] = "function"

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type": self.type,
            "function": {
                "name": self.function.name,
                "arguments": self.function.arguments,
            },
        }

    def to_str(self) -> str:
        """将 ToolInvocation 转换为字符串表示"""
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass(frozen=True)
class ModelGenerationConfig:
    """模型低频生成参数的统一封装。"""

    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 4096
    output_schema: ModelOutputSchema | None = None
    max_retries: int = 3


@dataclass(frozen=True)
class ModelMessage:
    """
    模型对话消息的标准结构。
    
    Attributes:
        role: 角色标识（如 "system", "user", "assistant"）。
        content: 消息内容载荷。
    """
    role: ModelMessageRole
    content: str | None
    tool_calls: tuple[ToolInvocation, ...] = ()
    tool_call_id: str | None = None
    name: str | None = None
    structured_content: Mapping[str, object] | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    @property
    def is_tool_message(self) -> bool:
        return self.role == "tool"


@dataclass(frozen=True)
class ModelToolResultMessage:
    """工具执行结果的一等领域模型。"""

    tool_call_id: str
    name: str
    content: str
    structured_output: Mapping[str, object] | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def to_model_message(self) -> ModelMessage:
        return ModelMessage(
            role="tool",
            content=self.content,
            tool_call_id=self.tool_call_id,
            name=self.name,
            structured_content=self.structured_output,
            metadata=dict(self.metadata),
        )


@dataclass(frozen=True, init=False)
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
    tools: tuple[CapabilityDescription, ...] = ()
    generation_config: ModelGenerationConfig = field(default_factory=ModelGenerationConfig)
    metadata: dict[str, object] = field(default_factory=dict)

    def __init__(
        self,
        *,
        messages: tuple[ModelMessage, ...],
        model_name: str | None = None,
        model_tag: str | None = None,
        tools: tuple[CapabilityDescription, ...] = (),
        generation_config: ModelGenerationConfig | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        output_schema: ModelOutputSchema | None = None,
        max_retries: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        resolved_generation_config = generation_config or ModelGenerationConfig()
        resolved_generation_config = replace(
            resolved_generation_config,
            temperature=temperature if temperature is not None else resolved_generation_config.temperature,
            top_p=top_p if top_p is not None else resolved_generation_config.top_p,
            max_tokens=max_tokens if max_tokens is not None else resolved_generation_config.max_tokens,
            output_schema=output_schema if output_schema is not None else resolved_generation_config.output_schema,
            max_retries=max_retries if max_retries is not None else resolved_generation_config.max_retries,
        )
        object.__setattr__(self, "messages", messages)
        object.__setattr__(self, "model_name", model_name)
        object.__setattr__(self, "model_tag", model_tag)
        object.__setattr__(self, "tools", tools)
        object.__setattr__(self, "generation_config", resolved_generation_config)
        object.__setattr__(self, "metadata", dict(metadata or {}))

    @property
    def temperature(self) -> float:
        return self.generation_config.temperature

    @property
    def top_p(self) -> float:
        return self.generation_config.top_p

    @property
    def max_tokens(self) -> int:
        return self.generation_config.max_tokens

    @property
    def output_schema(self) -> ModelOutputSchema | None:
        return self.generation_config.output_schema

    @property
    def max_retries(self) -> int:
        return self.generation_config.max_retries


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
    parsed: object | None = None
    tool_calls: tuple[ParsedToolCall, ...] = ()
    message: ModelMessage | None = None
    repair_reason: str | None = None
    raw: dict[str, object] = field(default_factory=dict)

    @property
    def assistant_message(self) -> ModelMessage | None:
        return self.message

    @property
    def tool_invocations(self) -> tuple[ToolInvocation, ...]:
        return tuple(item.invocation for item in self.tool_calls)
