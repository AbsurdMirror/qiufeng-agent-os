"""
model_provider.providers —— 具体 Provider 适配器实现集合。

当前内置：
- minimax: MiniMax 大模型适配器
- litellm_adapter: LiteLLM 通用适配器
"""
from .litellm_adapter import (
    LiteLLMRuntimeState,
    build_litellm_completion_payload,
    load_litellm_completion,
    normalize_litellm_response,
    probe_litellm_runtime,
)
from .minimax import (
    MiniMaxModelProviderClient,
    MiniMaxRuntimeState,
    is_minimax_request,
    probe_minimax_runtime,
)

__all__ = [
    "LiteLLMRuntimeState",
    "MiniMaxModelProviderClient",
    "MiniMaxRuntimeState",
    "build_litellm_completion_payload",
    "is_minimax_request",
    "load_litellm_completion",
    "normalize_litellm_response",
    "probe_litellm_runtime",
    "probe_minimax_runtime",
]
