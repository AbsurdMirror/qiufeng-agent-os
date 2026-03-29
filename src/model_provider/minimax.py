from dataclasses import dataclass, field
from os import getenv
from typing import Any

from src.model_provider.contracts import ModelRequest, ModelResponse
from src.model_provider.litellm_adapter import (
    build_litellm_completion_payload,
    load_litellm_completion,
    normalize_litellm_response,
    probe_litellm_runtime,
)


@dataclass(frozen=True)
class MiniMaxRuntimeState:
    litellm_installed: bool
    api_key_configured: bool
    available: bool
    status: str
    reason: str | None = None
    litellm_version: str | None = None
    configured_model: str | None = None
    base_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "litellm_installed": self.litellm_installed,
            "api_key_configured": self.api_key_configured,
            "available": self.available,
            "status": self.status,
            "reason": self.reason,
            "litellm_version": self.litellm_version,
            "configured_model": self.configured_model,
            "base_url": self.base_url,
            "metadata": dict(self.metadata),
        }


class MiniMaxModelProviderClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
        completion_callable: Any = None,
    ) -> None:
        self._api_key = api_key or getenv("QF_MINIMAX_API_KEY") or getenv("MINIMAX_API_KEY")
        self._model_name = model_name or getenv("QF_MINIMAX_MODEL") or getenv("MINIMAX_MODEL")
        self._base_url = (
            base_url or getenv("QF_MINIMAX_BASE_URL") or getenv("MINIMAX_BASE_URL")
        )
        self._completion_callable = completion_callable

    def probe_runtime(self) -> MiniMaxRuntimeState:
        return probe_minimax_runtime(
            api_key=self._api_key,
            model_name=self._model_name,
            base_url=self._base_url,
        )

    def invoke(self, request: ModelRequest) -> ModelResponse:
        runtime_state = self.probe_runtime()
        target_model_name = _resolve_minimax_target_model_name(request, self._model_name)
        if not runtime_state.available:
            return _build_degraded_response(
                request=request,
                runtime_state=runtime_state,
                target_model_name=target_model_name,
            )
        completion = self._completion_callable or load_litellm_completion()
        if completion is None:
            return _build_degraded_response(
                request=request,
                runtime_state=MiniMaxRuntimeState(
                    litellm_installed=runtime_state.litellm_installed,
                    api_key_configured=runtime_state.api_key_configured,
                    available=False,
                    status="degraded",
                    reason="litellm_completion_unavailable",
                    litellm_version=runtime_state.litellm_version,
                    configured_model=runtime_state.configured_model,
                    base_url=runtime_state.base_url,
                    metadata=dict(runtime_state.metadata),
                ),
                target_model_name=target_model_name,
            )
        payload = build_litellm_completion_payload(
            request,
            provider="minimax",
            api_key=self._api_key,
            base_url=self._base_url,
            default_model=target_model_name,
        )
        try:
            response = completion(**payload)
        except Exception as exc:
            return ModelResponse(
                model_name=f"minimax/{target_model_name}",
                content="",
                finish_reason="error",
                provider_id="minimax",
                usage=None,
                raw={
                    "provider": "minimax",
                    "status": "error",
                    "reason": "minimax_request_failed",
                    "message": str(exc),
                    "runtime": runtime_state.to_dict(),
                },
            )
        normalized = normalize_litellm_response(
            response,
            fallback_model_name=f"minimax/{target_model_name}",
            provider_id="minimax",
        )
        normalized_raw = dict(normalized.raw)
        normalized_raw["runtime"] = runtime_state.to_dict()
        return ModelResponse(
            model_name=normalized.model_name,
            content=normalized.content,
            finish_reason=normalized.finish_reason,
            provider_id=normalized.provider_id,
            usage=normalized.usage,
            raw=normalized_raw,
        )


def probe_minimax_runtime(
    *,
    api_key: str | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
) -> MiniMaxRuntimeState:
    litellm_state = probe_litellm_runtime()
    resolved_api_key = api_key or getenv("QF_MINIMAX_API_KEY") or getenv("MINIMAX_API_KEY")
    resolved_model_name = (
        model_name or getenv("QF_MINIMAX_MODEL") or getenv("MINIMAX_MODEL") or "abab6.5s-chat"
    )
    resolved_base_url = (
        base_url or getenv("QF_MINIMAX_BASE_URL") or getenv("MINIMAX_BASE_URL")
    )
    if not litellm_state.available:
        return MiniMaxRuntimeState(
            litellm_installed=litellm_state.litellm_installed,
            api_key_configured=bool(resolved_api_key),
            available=False,
            status="degraded",
            reason=litellm_state.reason,
            litellm_version=litellm_state.litellm_version,
            configured_model=resolved_model_name,
            base_url=resolved_base_url,
            metadata={"provider": "minimax"},
        )
    if not resolved_api_key:
        return MiniMaxRuntimeState(
            litellm_installed=True,
            api_key_configured=False,
            available=False,
            status="degraded",
            reason="minimax_api_key_missing",
            litellm_version=litellm_state.litellm_version,
            configured_model=resolved_model_name,
            base_url=resolved_base_url,
            metadata={"provider": "minimax"},
        )
    return MiniMaxRuntimeState(
        litellm_installed=True,
        api_key_configured=True,
        available=True,
        status="ready",
        litellm_version=litellm_state.litellm_version,
        configured_model=resolved_model_name,
        base_url=resolved_base_url,
        metadata={"provider": "minimax"},
    )


def is_minimax_request(request: ModelRequest) -> bool:
    provider_name = str(request.metadata.get("provider", "")).strip().lower()
    if provider_name == "minimax":
        return True
    model_tag = (request.model_tag or "").strip().lower()
    if model_tag in {"minimax", "provider.minimax", "model.minimax.chat"}:
        return True
    model_name = (request.model_name or "").strip().lower()
    return (
        model_name.startswith("minimax/")
        or model_name.startswith("minimax-")
        or model_name.startswith("abab")
    )


def _resolve_minimax_target_model_name(
    request: ModelRequest,
    default_model_name: str | None,
) -> str:
    raw_model_name = request.model_name or default_model_name or request.model_tag or "abab6.5s-chat"
    normalized = raw_model_name.strip()
    if normalized.lower().startswith("minimax/"):
        return normalized.split("/", maxsplit=1)[1]
    return normalized


def _build_degraded_response(
    *,
    request: ModelRequest,
    runtime_state: MiniMaxRuntimeState,
    target_model_name: str,
) -> ModelResponse:
    return ModelResponse(
        model_name=f"minimax/{target_model_name}",
        content="",
        finish_reason="error",
        provider_id="minimax",
        usage=None,
        raw={
            "provider": "minimax",
            "status": runtime_state.status,
            "reason": runtime_state.reason,
            "runtime": runtime_state.to_dict(),
            "request": {
                "model_name": request.model_name,
                "model_tag": request.model_tag,
                "message_count": len(request.messages),
            },
        },
    )
