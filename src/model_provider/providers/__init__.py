"""
model_provider.providers —— 具体 Provider 适配器实现集合。

当前内置：
- minimax: MiniMax 大模型适配器
- litellm_adapter: LiteLLM 通用适配器
"""
from .litellm_adapter import (
    LiteLLMRuntimeState,
    build_model_response,
    build_litellm_completion_payload,
    probe_litellm_runtime,
)
from .minimax import (
    MiniMaxModelProviderClient,
    MiniMaxRuntimeState,
)

__all__ = [
    "LiteLLMRuntimeState",
    "MiniMaxModelProviderClient",
    "MiniMaxRuntimeState",
    "build_model_response",
    "build_litellm_completion_payload",
    "probe_litellm_runtime",
]
