from dataclasses import dataclass, field
from typing import Any, Mapping
import litellm

from src.domain.models import ModelResponse
from src.domain.errors import ModelTokenOverflowError
from src.model_provider.contracts import RawModelProviderClient
from src.model_provider.providers.litellm_adapter import (
    probe_litellm_runtime, 
    LiteLLMAdapter,
    LiteLLMRawResponse,
)
from src.observability_hub.exports import ObservabilityHubExports


@dataclass
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


class MiniMaxModelProviderClient(RawModelProviderClient):
    """
    MiniMax 模型供应商的具体客户端实现。
    """
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
        observability: ObservabilityHubExports | None = None,
        adapter: LiteLLMAdapter | None = None,
    ) -> None:
        self.provider_id = "minimax"
        self._api_key = api_key
        self._model_name = model_name
        self._base_url = base_url
        self._observability = observability
        self._adapter = adapter or LiteLLMAdapter(observability=observability)

    def _record(self, trace_id: str | None, event: str, payload: Any, level: str = "DEBUG") -> None:
        if self._observability and trace_id:
            self._observability.record(trace_id, {"event": event, "payload": payload}, level)

    def _probe_runtime(self) -> MiniMaxRuntimeState:
        """探测当前运行环境是否满足调用 MiniMax 的条件"""
        litellm_state = probe_litellm_runtime()
        state = MiniMaxRuntimeState(
            litellm_installed=litellm_state.litellm_installed,
            api_key_configured=bool(self._api_key),
            available=False,
            status="degraded",
            reason=None,
            litellm_version=litellm_state.litellm_version,
            configured_model=self._model_name,
            base_url=self._base_url,
            metadata={"provider": "minimax"},
        )
        if not litellm_state.available:
            state.reason = litellm_state.reason
            return state
        if not self._api_key:
            state.reason = "minimax_api_key_missing"
            return state
        if not self._model_name:
            state.reason = "minimax_model_missing"
            return state
        
        state.available = True
        state.status = "ready"
        return state

    def completion(self, payload: Mapping[str, Any]) -> LiteLLMRawResponse:
        """
        MiniMax 的唯一模型调用入口。

        该函数只做两件事：
        1. 运行时条件检查（依赖/API Key/模型配置）；
        2. 调用 LiteLLM completion 并返回 LiteLLM 标准 raw 响应。
        """
        runtime_state = self._probe_runtime()
        if not runtime_state.available:
            return _build_degraded_response(
                runtime_state=runtime_state,
            )
        payload_dict = dict(payload)
        payload_dict.setdefault("api_key", self._api_key)
        payload_dict.setdefault("base_url", self._base_url)
        
        trace_id = payload_dict.get("metadata", {}).get("trace_id")

        # 注入模型成本元数据
        fake_model_cost = {
            "max_tokens": 64 * 1024,
            "input_cost_per_token": 0.000001,
            "output_cost_per_token": 0.000002,
            "lite_llm_model_name": "MiniMax-M2.7",
            "model_name": "minimax/MiniMax-M2.7"
        }
        litellm.model_cost["minimax/MiniMax-M2.7"] = fake_model_cost
        litellm.model_cost["minimax/MiniMax-M2.7-highspeed"] = fake_model_cost
        litellm.model_cost["minimax/MiniMax-M2.5-highspeed"] = fake_model_cost

        try:
            # 计算需要预留给模型输出的 Token 数
            reserved_output_tokens = None
            max_tokens = payload_dict.get("max_tokens")
            if isinstance(max_tokens, int) and max_tokens > 0:
                reserved_output_tokens = max_tokens

            # 调用适配器进行裁剪与归一化 (包含 System Merging)
            if payload_dict.get("messages"):
                payload_dict["messages"] = self._adapter.trim_messages(
                    payload_dict["messages"],
                    model=self._model_name or "gpt-3.5-turbo",
                    trim_ratio=0.75,
                    reserved_output_tokens=reserved_output_tokens,
                    trace_id=trace_id,
                )

            # litellm._turn_on_debug()
            response = litellm.completion(**payload_dict)
        except ModelTokenOverflowError as exc:
            from src.domain.errors import format_user_facing_error

            message = format_user_facing_error(
                exc,
                summary="MiniMax 请求 Token 超限",
            )
            print(message)

            return ModelResponse(
                success=False,
                model_name=self._model_name or "minimax-model",
                content="",
                finish_reason="error",
                provider_id=self.provider_id,
                repair_reason="token_limit_exceeded",
                raw={
                    "reason": "token_limit_exceeded",
                    "message": message,
                    "budget": exc.budget,
                    "actual": exc.actual,
                    "runtime": runtime_state.to_dict(),
                },
            )
        except Exception as exc:
            from src.domain.errors import format_user_facing_error

            raise RuntimeError(
                format_user_facing_error(
                    exc,
                    summary="MiniMax 请求失败",
                )
            ) from exc
        return response


def _build_degraded_response(
    runtime_state: MiniMaxRuntimeState,
) -> ModelResponse:
    """构造 LiteLLM 兼容的降级 raw 响应。"""
    return ModelResponse(
        success=False,
        model_name="minimax-model",
        content="",
        finish_reason="error",
        provider_id="minimax",
        repair_reason=runtime_state.reason or "minimax_runtime_unavailable",
        raw={
            "status": runtime_state.status,
            "reason": runtime_state.reason or "minimax_runtime_unavailable",
            "runtime": runtime_state.to_dict(),
        },
    )
