from dataclasses import dataclass, field
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from typing import Any, Mapping

from src.model_provider.contracts import ModelRequest, ModelResponse, ModelUsage


@dataclass(frozen=True)
class LiteLLMRuntimeState:
    litellm_installed: bool
    available: bool
    status: str
    reason: str | None = None
    litellm_version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "litellm_installed": self.litellm_installed,
            "available": self.available,
            "status": self.status,
            "reason": self.reason,
            "litellm_version": self.litellm_version,
            "metadata": dict(self.metadata),
        }


def probe_litellm_runtime() -> LiteLLMRuntimeState:
    litellm_installed = _has_dependency("litellm")
    litellm_version = _read_dependency_version("litellm")
    if litellm_installed:
        return LiteLLMRuntimeState(
            litellm_installed=True,
            available=True,
            status="ready",
            litellm_version=litellm_version,
            metadata={"provider": "litellm"},
        )
    return LiteLLMRuntimeState(
        litellm_installed=False,
        available=False,
        status="degraded",
        reason="litellm_dependency_missing",
        litellm_version=litellm_version,
        metadata={"provider": "litellm"},
    )


def build_litellm_completion_payload(
    request: ModelRequest,
    *,
    provider: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    default_model: str | None = None,
) -> dict[str, Any]:
    model_name = _resolve_model_name(
        request=request,
        provider=provider,
        default_model=default_model,
    )
    payload: dict[str, Any] = {
        "model": model_name,
        "messages": tuple(
            {"role": message.role, "content": message.content}
            for message in request.messages
        ),
    }
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.top_p is not None:
        payload["top_p"] = request.top_p
    if request.max_tokens is not None:
        payload["max_tokens"] = request.max_tokens
    if api_key:
        payload["api_key"] = api_key
    if base_url:
        payload["base_url"] = base_url
    metadata = dict(request.metadata)
    litellm_kwargs = metadata.pop("litellm_kwargs", None)
    if metadata:
        payload["metadata"] = metadata
    if isinstance(litellm_kwargs, Mapping):
        payload.update(dict(litellm_kwargs))
    return payload


def normalize_litellm_response(
    response: Any,
    *,
    fallback_model_name: str,
    provider_id: str,
) -> ModelResponse:
    raw = _to_mapping(response)
    usage_payload = raw.get("usage")
    usage = _normalize_usage(usage_payload if isinstance(usage_payload, Mapping) else {})
    first_choice = _read_first_choice(raw)
    finish_reason = _read_string(first_choice.get("finish_reason"))
    content = _extract_choice_content(first_choice)
    model_name = _read_string(raw.get("model")) or fallback_model_name
    return ModelResponse(
        model_name=model_name,
        content=content,
        finish_reason=finish_reason,
        provider_id=provider_id,
        usage=usage,
        raw=raw,
    )


def load_litellm_completion() -> Any:
    if not _has_dependency("litellm"):
        return None
    module = import_module("litellm")
    completion = getattr(module, "completion", None)
    return completion if callable(completion) else None


def _resolve_model_name(
    request: ModelRequest,
    *,
    provider: str | None,
    default_model: str | None,
) -> str:
    raw_model_name = request.model_name or default_model or request.model_tag or "mock-model"
    if provider == "minimax":
        normalized = raw_model_name.strip()
        if normalized.lower().startswith("minimax/"):
            return normalized
        return f"minimax/{normalized}"
    return raw_model_name.strip()


def _normalize_usage(usage_payload: Mapping[str, Any]) -> ModelUsage | None:
    if not usage_payload:
        return None
    input_tokens = _read_int(
        usage_payload.get("prompt_tokens") or usage_payload.get("input_tokens")
    )
    output_tokens = _read_int(
        usage_payload.get("completion_tokens") or usage_payload.get("output_tokens")
    )
    total_tokens = _read_int(usage_payload.get("total_tokens"))
    return ModelUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _read_first_choice(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    choices = raw.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, Mapping):
            return first_choice
        return _to_mapping(first_choice)
    return {}


def _extract_choice_content(choice: Mapping[str, Any]) -> str:
    message = choice.get("message")
    if isinstance(message, Mapping):
        return _normalize_content(message.get("content"))
    if message is not None:
        return _normalize_content(_to_mapping(message).get("content"))
    return _normalize_content(choice.get("text"))


def _normalize_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        chunks = []
        for item in value:
            if isinstance(item, Mapping):
                text_value = item.get("text") or item.get("content")
                if text_value is not None:
                    chunks.append(str(text_value))
            elif item is not None:
                chunks.append(str(item))
        return "".join(chunks)
    return str(value)


def _to_mapping(data: Any) -> dict[str, Any]:
    if isinstance(data, Mapping):
        return dict(data)
    model_dump = getattr(data, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    dict_method = getattr(data, "dict", None)
    if callable(dict_method):
        dumped = dict_method()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    return {}


def _read_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _read_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _has_dependency(module_name: str) -> bool:
    return find_spec(module_name) is not None


def _read_dependency_version(package_name: str) -> str | None:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return None
