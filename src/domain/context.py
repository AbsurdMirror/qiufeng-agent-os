from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from src.domain.models import ModelMessage

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | tuple["JSONValue", ...] | dict[str, "JSONValue"]

ContextBlockKind: TypeAlias = Literal[
    "user_turn",
    "assistant_answer",
    "tool_interaction",
]

SystemPromptPartSource: TypeAlias = Literal[
    "base_prompt",
    "profile_patch",
    "memory_snippet",
]


@dataclass(frozen=True)
class ContextBudget:
    max_input_tokens: int
    reserved_output_tokens: int
    trim_ratio: float


@dataclass(frozen=True)
class SystemPromptPart:
    source: SystemPromptPartSource
    content: str


@dataclass(frozen=True)
class ContextBlock:
    block_id: str
    kind: ContextBlockKind
    messages: tuple[ModelMessage, ...]
    token_count: int


@dataclass(frozen=True)
class ContextLoadRequest:
    logic_id: str
    session_id: str
    budget: ContextBudget
    include_profile_patch: bool
    include_memory_snippets: bool
    history_block_limit: int


@dataclass(frozen=True)
class ContextLoadResult:
    system_parts: tuple[SystemPromptPart, ...]
    history_blocks: tuple[ContextBlock, ...]


@dataclass(frozen=True)
class RuntimeMemorySnapshot:
    system_parts: tuple[SystemPromptPart, ...] = ()
    history_blocks: tuple[ContextBlock, ...] = ()
