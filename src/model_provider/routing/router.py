from typing import Any
from src.model_provider.contracts import ModelRequest, ModelResponse, ModelProviderClient, ModelMessage

import os

try:
    # Set TIKTOKEN_CACHE_DIR to prevent synchronous network downloads if local cache is available
    if not os.environ.get("TIKTOKEN_CACHE_DIR"):
        os.environ["TIKTOKEN_CACHE_DIR"] = "/tmp/tiktoken_cache"
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False

class ModelRouter(ModelProviderClient):
    """
    模型路由分发器 (Model Routing)
    实现 T4 阶段的 MP-P0-01 (名称匹配) 和 MP-P0-02 (自动裁剪)
    它就像个智能电话分机：接到请求后，先拿着"剪刀"把超长对话剪短，再根据名字呼叫确切的大模型实例。
    """
    def __init__(self, clients: dict[str, ModelProviderClient]):
        """
        :param clients: A dictionary mapping model names or logical tags to specific client implementations.
        """
        self._clients = clients
        # 默认上下文窗口限制
        self._context_windows = {
            "gpt-3.5-turbo": 4096,
            "gpt-4": 8192,
            "minimax": 32000,
            "default": 4096
        }

    def _trim_messages(self, messages: tuple[ModelMessage, ...], model_name: str) -> tuple[ModelMessage, ...]:
        """
        MP-P0-02: 自动裁剪 (Auto Trimming)
        基于目标模型的上下文窗口对输入消息进行裁剪，由于上下文可能突破界限，
        这里采用强制保留 System 提示词，并从最新的（尾部）对话开始倒推凑配额。
        """
        max_tokens = self._context_windows.get(model_name, self._context_windows["default"])

        def estimate_tokens(text: str) -> int:
            if HAS_TIKTOKEN:
                try:
                    encoding = tiktoken.encoding_for_model(model_name)
                except KeyError:
                    encoding = tiktoken.get_encoding("cl100k_base")
                return len(encoding.encode(text))
            else:
                # 粗暴但稳妥的降级：如果没有 tiktoken 包，干脆按英文字符长度除以 4 凑合算一下
                return len(text) // 4

        total_tokens = 0
        trimmed_messages = []

        # 永远保留 system message 如果有的话
        system_messages = [m for m in messages if m.role == "system"]
        for msg in system_messages:
            total_tokens += estimate_tokens(msg.content)

        # 倒序遍历剩下的消息，直到填满上下文窗口
        other_messages = [m for m in messages if m.role != "system"]

        # 预留 500 tokens 给模型回答
        available_tokens = max_tokens - total_tokens - 500

        for msg in reversed(other_messages):
            msg_tokens = estimate_tokens(msg.content)
            if available_tokens - msg_tokens > 0:
                trimmed_messages.append(msg)
                available_tokens -= msg_tokens
            else:
                break

        # 组合 system messages 和裁剪后的其他消息
        return tuple(system_messages + trimmed_messages[::-1])

    def invoke(self, request: ModelRequest) -> ModelResponse:
        """
        MP-P0-01: 显式名称匹配 (Explicit Name Matching)
        基于物理名称 (Model Name) 的直接调度匹配机制
        """
        target_name = request.model_name or request.model_tag or "default"

        # MP-P0-02: 自动裁剪
        trimmed_messages = self._trim_messages(request.messages, target_name)

        # 构建新的请求对象
        trimmed_request = ModelRequest(
            messages=trimmed_messages,
            model_name=request.model_name,
            model_tag=request.model_tag,
            temperature=request.temperature,
            top_p=request.top_p,
            max_tokens=request.max_tokens,
            metadata=request.metadata
        )

        # MP-P0-01: 路由匹配
        client = self._clients.get(target_name)
        if not client:
            client = self._clients.get("default")

        if not client:
            raise ValueError(f"No suitable model provider found for '{target_name}'")

        return client.invoke(trimmed_request)
