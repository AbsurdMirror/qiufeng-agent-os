import pytest
from src.domain.context import (
    ContextBlock,
    ContextBudget,
    ContextLoadRequest,
    ContextLoadResult,
    RuntimeMemorySnapshot,
    SystemPromptPart,
)
from src.domain.models import ModelMessage


def test_context_budget_creation():
    budget = ContextBudget(
        max_input_tokens=1000,
        reserved_output_tokens=500,
        trim_ratio=0.75
    )
    assert budget.max_input_tokens == 1000
    assert budget.reserved_output_tokens == 500
    assert budget.trim_ratio == 0.75


def test_system_prompt_part_creation():
    part = SystemPromptPart(source="base_prompt", content="Hello")
    assert part.source == "base_prompt"
    assert part.content == "Hello"


def test_context_block_creation():
    msg = ModelMessage(role="user", content="hi")
    block = ContextBlock(
        block_id="blk-1",
        kind="user_turn",
        messages=(msg,),
        token_count=10
    )
    assert block.block_id == "blk-1"
    assert block.kind == "user_turn"
    assert block.messages == (msg,)
    assert block.token_count == 10


def test_runtime_memory_snapshot_defaults():
    snapshot = RuntimeMemorySnapshot()
    assert snapshot.system_parts == ()
    assert snapshot.history_blocks == ()


def test_context_load_result_creation():
    part = SystemPromptPart(source="base_prompt", content="Hello")
    block = ContextBlock(
        block_id="blk-1",
        kind="user_turn",
        messages=(),
        token_count=0
    )
    result = ContextLoadResult(
        system_parts=(part,),
        history_blocks=(block,)
    )
    assert result.system_parts == (part,)
    assert result.history_blocks == (block,)


def test_context_load_request_creation():
    budget = ContextBudget(100, 50, 0.5)
    request = ContextLoadRequest(
        logic_id="l-1",
        session_id="s-1",
        budget=budget,
        include_profile_patch=True,
        include_memory_snippets=False,
        history_block_limit=5
    )
    assert request.logic_id == "l-1"
    assert request.budget == budget
    assert request.include_profile_patch is True
    assert request.history_block_limit == 5
