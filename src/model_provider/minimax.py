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
    """
    MiniMax 模型供应商的具体客户端实现。
    
    设计意图：
    负责封装与 MiniMax 大模型 API 通信的具体细节。
    它依赖 LiteLLM 库来进行实际的网络请求，但在调用前会先进行“运行时探测”，
    以实现环境隔离与优雅降级（缺少依赖时不会崩溃，而是返回包含错误信息的标准化结果）。
    """
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
        """探测当前运行环境是否满足调用 MiniMax 的条件（例如是否配置了 API Key）"""
        return probe_minimax_runtime(
            api_key=self._api_key,
            model_name=self._model_name,
            base_url=self._base_url,
        )

    def invoke(self, request: ModelRequest) -> ModelResponse:
        """执行模型推理请求"""
        runtime_state = self.probe_runtime()
        target_model_name = _resolve_minimax_target_model_name(request, self._model_name)
        
        # 优点：优雅降级。如果缺少依赖或 Key，不抛异常，而是返回结构化的错误响应
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
    """
    通过启发式规则判断当前请求是否旨在调用 MiniMax 模型。
    
    设计意图：
    由于请求的 `ModelRequest` 可能来自各种渠道（有些传 provider，有些传模型全称，有些传自定义 tag），
    我们需要一个集中的地方来猜测请求的意图。这是一种典型的“基于规则的路由判定”策略。
    
    判断优先级：
    1. 显式指定了 metadata 中的 provider 为 "minimax"。
    2. model_tag 包含 "minimax" 相关标识。
    3. model_name 以 "minimax" 或 "abab"（MiniMax 模型的特有前缀）开头。
    """
    # 提取 provider，去除两端空格并转小写以实现宽容匹配
    provider_name = str(request.metadata.get("provider", "")).strip().lower()
    if provider_name == "minimax":
        return True
    
    # 提取 model_tag 进行宽容匹配
    model_tag = (request.model_tag or "").strip().lower()
    if model_tag in {"minimax", "provider.minimax", "model.minimax.chat"}:
        return True
    
    # 提取 model_name 检查特征前缀
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
    """
    解析最终要请求的 MiniMax 模型名称。
    
    设计意图：
    请求中可能传入了带有厂商前缀的模型名（例如 "minimax/abab6.5s-chat"），
    但在真正通过 LiteLLM 调用 MiniMax API 时，我们只需要纯粹的模型名称（"abab6.5s-chat"）。
    这个函数负责提取干净的模型名，并在未提供时给出默认兜底。
    
    缺点与风险 (P0 级)：
    硬编码回退到了 "abab6.5s-chat" 模型。如果未来该模型下线或调整计费，
    修改代码的成本较高，这种全局兜底应当通过统一的环境变量或系统配置文件进行动态管理。
    """
    # 优先级：请求的模型名 > 实例化时传入的默认名 > 请求的 tag > 最后的硬编码兜底
    raw_model_name = request.model_name or default_model_name or request.model_tag or "abab6.5s-chat"
    normalized = raw_model_name.strip()
    
    # 如果模型名是以 "minimax/" 开头，使用 split 切割并只保留后面的实际模型名
    if normalized.lower().startswith("minimax/"):
        return normalized.split("/", maxsplit=1)[1]
    
    return normalized


def _build_degraded_response(
    *,
    request: ModelRequest,
    runtime_state: MiniMaxRuntimeState,
    target_model_name: str,
) -> ModelResponse:
    """
    构造一个降级（失败）的标准化响应。
    
    设计意图：
    当环境探测发现缺少依赖包或缺少 API Key 时，与其抛出致命异常（Exception）让程序崩溃，
    不如返回一个符合 `ModelResponse` 契约的对象，并将其 `finish_reason` 标记为 "error"。
    这样编排层能够捕获并处理这个错误，进而给用户返回友好的提示。
    """
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
