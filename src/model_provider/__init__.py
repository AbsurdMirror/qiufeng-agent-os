"""
模型抽象层 (Model Provider) 模块入口。

设计意图：
作为该层对外的唯一暴露点（Facade Pattern，外观模式），统一导出内部的模型契约、初始化引导函数以及特定的模型适配器（如 LiteLLM 和 MiniMax）。
外部模块只需要通过 `from src.model_provider import ...` 即可使用，无需感知内部文件结构的划分。

初学者提示：
这里的 `__all__` 列表非常重要，它不仅告诉 Python 当执行 `from ... import *` 时该导出什么，
更像是这个模块的“目录”，清晰地展示了本模块对外提供的所有公开 API。
"""
from .bootstrap import initialize
from .contracts import (
    InMemoryModelProviderClient,
    ModelMessage,
    ModelProviderClient,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)
from .exports import ModelProviderExports
from .litellm_adapter import (
    LiteLLMRuntimeState,
    build_litellm_completion_payload,
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
    "InMemoryModelProviderClient",
    "LiteLLMRuntimeState",
    "ModelMessage",
    "ModelProviderClient",
    "ModelProviderExports",
    "ModelRequest",
    "ModelResponse",
    "ModelUsage",
    "MiniMaxModelProviderClient",
    "MiniMaxRuntimeState",
    "build_litellm_completion_payload",
    "initialize",
    "is_minimax_request",
    "normalize_litellm_response",
    "probe_litellm_runtime",
    "probe_minimax_runtime",
]
