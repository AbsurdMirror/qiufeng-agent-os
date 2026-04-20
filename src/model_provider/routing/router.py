from typing import Any
from src.domain.models import ModelMessage, ModelRequest, ModelResponse
from src.model_provider.contracts import ModelProviderClient
from src.model_provider.providers.litellm_adapter import (
    build_litellm_completion_payload,
    build_model_response,
)

import os
import tempfile

try:
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
        if not os.environ.get("TIKTOKEN_CACHE_DIR"):
            os.environ["TIKTOKEN_CACHE_DIR"] = os.path.join(
                tempfile.gettempdir(),
                "tiktoken_cache",
            )
        # 默认上下文窗口限制
        self._context_windows = {
            "gpt-3.5-turbo": 4096,
            "gpt-4": 8192,
            "minimax": 32000,
            "default": 4096
        }

    def add_client(self, model_name: str, client: ModelProviderClient) -> None:
        self._clients[model_name] = client

    def _build_repair_message(self, *, invalid_output: str, error_text: str) -> ModelMessage:
        return ModelMessage(
            role="user",
            content=(
                "你的上一次输出在解析阶段出错，请严格按照本轮规范重新输出。\n"
                "要求：只输出符合规范的结果，不要附加解释文本。\n"
                f"上一次输出: {invalid_output}\n"
                f"解析错误: {error_text}"
            ),
        )

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

    def completion(self, request: ModelRequest) -> ModelResponse:
        """
        MP-P0-01: 显式名称匹配 (Explicit Name Matching)
        基于物理名称 (Model Name) 的直接调度匹配机制
        """
        # P0 级修复：简化路由逻辑，直接以 model_name 为主索引
        target_name = request.model_name or "default"

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
            tools=request.tools,
            response_parse=request.response_parse,
            metadata=request.metadata
        )

        # MP-P0-01: 路由匹配
        client = self._clients.get(target_name)
        if not client:
            client = self._clients.get("default")

        if not client:
            raise ValueError(f"No suitable model provider found for '{target_name}'")

        response_parse = trimmed_request.response_parse
        max_retries_raw = response_parse.schema_max_retries
        max_retries = max_retries_raw if isinstance(max_retries_raw, int) and max_retries_raw >= 0 else 0
        output_schema = response_parse.output_schema
        current_request = trimmed_request
        attempts = 0
        while True:
            try:
                provider_id = client.provider_id
                payload = build_litellm_completion_payload(
                    current_request,
                )
                raw = client.completion(payload)
                # print("DEBUG", "model output 原始 raw: ", raw)
                response = build_model_response(
                    raw,
                    request=current_request,
                    output_schema=output_schema,
                    fallback_model_name=current_request.model_name or target_name,
                    provider_id=provider_id,
                )
            except Exception as exc:  # noqa: BLE001
                fallback = ModelResponse(
                    model_name=current_request.model_name or target_name,
                    content="",
                    success=False,
                    finish_reason="error",
                    provider_id=target_name,
                    repair_reason=str(exc),
                    raw={
                        "reason": "model_router_completion_failed",
                        "message": str(exc),
                        "traceback": __import__('traceback').format_exc(),
                    },
                )
                response = fallback

            if response.success:
                return response
            if attempts >= max_retries:
                exhausted_raw = dict(response.raw)
                exhausted_raw.setdefault("reason", "model_response_parse_failed")
                exhausted_raw.setdefault("message", "response parsing failed after retries")
                exhausted_raw["retry_count"] = attempts
                return ModelResponse(
                    model_name=response.model_name,
                    content=response.content,
                    success=False,
                    finish_reason="error",
                    provider_id=response.provider_id,
                    usage=response.usage,
                    parsed=response.parsed,
                    tool_calls=response.tool_calls,
                    repair_reason=response.repair_reason,
                    raw=exhausted_raw,
                )
            attempts += 1
            repair_reason = response.repair_reason or "model_response_parse_failed"
            repair_message = self._build_repair_message(
                invalid_output=response.content,
                error_text=repair_reason,
            )
            current_request = ModelRequest(
                messages=current_request.messages + (repair_message,),
                model_name=current_request.model_name,
                model_tag=current_request.model_tag,
                temperature=current_request.temperature,
                top_p=current_request.top_p,
                max_tokens=current_request.max_tokens,
                tools=current_request.tools,
                response_parse=current_request.response_parse,
                metadata=current_request.metadata,
            )
