from unittest.mock import MagicMock

import litellm
from pydantic import BaseModel

from src.domain.capabilities import CapabilityDescription
from src.domain.models import ModelGenerationConfig, ModelRequest
from src.model_provider.providers.litellm_adapter import LiteLLMAdapter


class _StructuredAnswer(BaseModel):
    answer: str


def _build_request(*, tools: tuple[CapabilityDescription, ...] = ()) -> ModelRequest:
    return ModelRequest(
        messages=(),
        model_name="minimax/MiniMax-M2.7",
        tools=tools,
    )


def _build_mock_response(
    *,
    content: str | None,
    tool_calls: list[dict[str, object]] | None = None,
    finish_reason: str = "stop",
) -> litellm.ModelResponse:
    mock_response = MagicMock(spec=litellm.ModelResponse)
    mock_choice = MagicMock()
    mock_choice.finish_reason = finish_reason
    mock_choice.message = MagicMock()
    mock_choice.message.content = content
    mock_choice.message.role = "assistant"
    mock_choice.message.tool_calls = tool_calls
    mock_choice.message.function_call = None
    mock_response.choices = [mock_choice]

    mock_usage = MagicMock()
    mock_usage.completion_tokens = 10
    mock_usage.prompt_tokens = 20
    mock_usage.total_tokens = 30
    mock_response.usage = mock_usage
    mock_response.model = "minimax/MiniMax-M2.7"
    return mock_response


def _build_tool(capability_id: str) -> CapabilityDescription:
    return CapabilityDescription(
        capability_id=capability_id,
        domain="tool",
        name=capability_id,
        description=f"tool {capability_id}",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
    )


def test_model_request_supports_default_and_explicit_generation_config():
    request = ModelRequest(messages=(), model_name="demo")
    assert request.temperature == 0.0
    assert request.top_p == 1.0
    assert request.max_tokens == 4096
    assert request.max_retries == 3

    explicit_request = ModelRequest(
        messages=(),
        model_name="demo",
        generation_config=ModelGenerationConfig(temperature=0.4, top_p=0.9, max_tokens=1024, max_retries=5),
    )
    assert explicit_request.temperature == 0.4
    assert explicit_request.top_p == 0.9
    assert explicit_request.max_tokens == 1024
    assert explicit_request.max_retries == 5


def test_build_model_response_keeps_content_and_multiple_tool_calls():
    adapter = LiteLLMAdapter()
    tools = (_build_tool("tool.first"), _build_tool("tool.second"))
    request = _build_request(tools=tools)
    mock_response = _build_mock_response(
        content="我先去查两个工具。",
        tool_calls=[
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "tool.first", "arguments": '{"value":"a"}'},
            },
            {
                "id": "call-2",
                "type": "function",
                "function": {"name": "tool.second", "arguments": '{"value":"b"}'},
            },
        ],
    )

    result = adapter.build_model_response(
        response_raw=mock_response,
        request=request,
        output_schema=None,
        fallback_model_name="fallback-model",
        provider_id="minimax",
    )

    assert result.success is True
    assert result.content == "我先去查两个工具。"
    assert len(result.tool_calls) == 2
    assert len(result.tool_invocations) == 2
    assert result.assistant_message is not None
    assert result.assistant_message.content == "我先去查两个工具。"
    assert len(result.assistant_message.tool_calls) == 2


def test_build_model_response_reports_invalid_tool_arguments():
    adapter = LiteLLMAdapter()
    request = _build_request(tools=(_build_tool("tool.first"),))
    mock_response = _build_mock_response(
        content=None,
        tool_calls=[
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "tool.first", "arguments": '{"value":'},
            }
        ],
    )

    result = adapter.build_model_response(
        response_raw=mock_response,
        request=request,
        output_schema=None,
        fallback_model_name="fallback-model",
        provider_id="minimax",
    )

    assert result.success is False
    assert result.finish_reason == "tool_call_error"
    assert result.raw["reason"] == "tool_calls_parse_failed"
    assert isinstance(result.raw["tool_error"], dict)
    assert result.raw["tool_error"]["reason_code"] == "tool_call_arguments_must_be_valid_json"


def test_build_model_response_keeps_tool_calls_when_content_schema_invalid():
    adapter = LiteLLMAdapter()
    request = _build_request(tools=(_build_tool("tool.first"),))
    mock_response = _build_mock_response(
        content='{"not_answer":"x"}',
        tool_calls=[
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "tool.first", "arguments": '{"value":"x"}'},
            }
        ],
    )

    result = adapter.build_model_response(
        response_raw=mock_response,
        request=request,
        output_schema=_StructuredAnswer,
        fallback_model_name="fallback-model",
        provider_id="minimax",
    )

    assert result.success is True
    assert len(result.tool_calls) == 1
    assert result.repair_reason is not None


def test_build_model_response_parses_structured_content_without_tool_calls():
    adapter = LiteLLMAdapter()
    request = _build_request()
    mock_response = _build_mock_response(content='{"answer":"done"}')

    result = adapter.build_model_response(
        response_raw=mock_response,
        request=request,
        output_schema=_StructuredAnswer,
        fallback_model_name="fallback-model",
        provider_id="minimax",
    )

    assert result.success is True
    assert isinstance(result.parsed, _StructuredAnswer)
    assert result.parsed.answer == "done"