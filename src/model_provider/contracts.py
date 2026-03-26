from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ModelMessage:
    role: str
    content: str


@dataclass(frozen=True)
class ModelRequest:
    messages: tuple[ModelMessage, ...]
    model_name: str | None = None
    model_tag: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class ModelResponse:
    model_name: str
    content: str
    finish_reason: str | None = None
    provider_id: str | None = None
    usage: ModelUsage | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class ModelProviderClient(Protocol):
    def invoke(self, request: ModelRequest) -> ModelResponse:
        raise NotImplementedError


class InMemoryModelProviderClient:
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
