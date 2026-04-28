from dataclasses import dataclass, field
from typing import Any, Mapping
import litellm

from src.domain.models import ModelResponse
from src.model_provider.contracts import RawModelProviderClient, LiteLLMRawResponse
from src.model_provider.providers.litellm_adapter import (
    probe_litellm_runtime
)


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
    
    设计意图：
    负责封装与 MiniMax 大模型 API 通信的具体细节。
    它依赖 LiteLLM 库来进行实际的网络请求，但在调用前会先进行"运行时探测"，
    以实现环境隔离与优雅降级（缺少依赖时不会崩溃，而是返回包含错误信息的标准化结果）。
    """
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.provider_id = "minimax"
        self._api_key = api_key
        self._model_name = model_name
        self._base_url = base_url

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

        # 注入模型成本元数据，以便裁剪器能正确获取 context_window
        fake_model_cost = {
            "max_tokens": 64 * 1024,
            "input_cost_per_token": 0.000001,  # 随便填个数，防止计费逻辑崩溃
            "output_cost_per_token": 0.000002,
            "lite_llm_model_name": "MiniMax-M2.7",
            "model_name": "minimax/MiniMax-M2.7"
        }
        litellm.model_cost["minimax/MiniMax-M2.7"] = fake_model_cost
        litellm.model_cost["minimax/MiniMax-M2.7-highspeed"] = fake_model_cost
        litellm.model_cost["minimax/MiniMax-M2.5-highspeed"] = fake_model_cost

        # 处理 MiniMax 限制：messages 中只能有一个 system message
        raw_messages = payload_dict.get("messages", [])
        if raw_messages:
            system_contents = []
            other_messages = []
            for msg in raw_messages:
                if msg.get("role") == "system":
                    content = msg.get("content")
                    if content:
                        system_contents.append(str(content))
                else:
                    other_messages.append(msg)
            
            merged_messages = []
            if system_contents:
                merged_messages.append({
                    "role": "system",
                    "content": "\n\n".join(system_contents)
                })
            merged_messages.extend(other_messages)
            
            payload_dict["messages"] = merged_messages

        """
        # 调用自定义裁剪器（基于 litellm.token_counter）
        if payload_dict.get("messages"):
            payload_dict["messages"] = trim_messages(
                payload_dict["messages"],
                model=self._model_name,
                trim_ratio=0.75,
            )
        """

        try:
            # litellm._turn_on_debug()
            # print("payload_dict", payload_dict)
            response = litellm.completion(**payload_dict)
        except Exception as exc:
            return ModelResponse(
                success=False,
                model_name=self._model_name or "minimax-model",
                content="",
                finish_reason="error",
                provider_id=self.provider_id,
                repair_reason="minimax_request_failed",
                raw={
                    "reason": "minimax_request_failed",
                    "message": str(exc),
                    "runtime": runtime_state.to_dict(),
                },
            )
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
