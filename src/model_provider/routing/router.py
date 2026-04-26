from typing import Any, Annotated
from pydantic import Field
from src.domain.models import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
)
from src.domain.decorators import qfaos_pytool
from src.model_provider.contracts import ModelProviderClient, RawModelProviderClient
from src.model_provider.providers.litellm_adapter import (
    build_litellm_completion_payload,
    build_model_response,
)

import os

from src.observability_hub.exports import ObservabilityHubExports

class ModelRouter(ModelProviderClient):
    """
    模型路由分发器 (Model Routing)
    实现 T4 阶段的 MP-P0-01 (名称匹配)
    它就像个智能电话分机：接到请求后，根据名字呼叫确切的大模型实例。
    """
    def __init__(self, clients: dict[str, RawModelProviderClient], observability: ObservabilityHubExports | None = None):
        """
        :param clients: A dictionary mapping model names or logical tags to specific client implementations.
        :param observability: 可选的监控模块导出对象。
        """
        self._clients = clients
        self._observability = observability

    def add_client(self, model_name: str, client: RawModelProviderClient) -> None:
        self._clients[model_name] = client

    def _build_repair_message(self, *, invalid_output: str, error_text: str, finish_reason: str) -> ModelMessage:
        return ModelMessage(
            role="user",
            content=(
                "你的上一次"
                "工具调用" if finish_reason == "SchemaValidationError" else "输出"
                "在解析阶段出错，请严格按照本轮规范重新输出。\n"
                "要求：只输出符合规范的结果，不要附加解释文本。\n"
                "上一次"
                "工具调用" if finish_reason == "SchemaValidationError" else "输出"
                f"为: {invalid_output}\n"
                f"解析错误: {error_text}"
            ),
        )

    @qfaos_pytool(id="model.completion", domain="model")
    def completion(
        self,
        request: Annotated[ModelRequest, Field(description="模型补全请求对象")],
    ) -> Annotated[ModelResponse, Field(description="模型补全响应对象")]:
        """
        MP-P0-01: 显式名称匹配 (Explicit Name Matching)
        基于物理名称 (Model Name) 的直接调度匹配机制
        """
        # MP-P0-01: 路由匹配
        client = self._clients.get(request.model_name)
        if not client:
            raise ValueError(f"No suitable model provider found for '{request.model_name}'")

        trace_id = request.metadata.get("trace_id", "unknown")

        max_retries = request.max_retries
        output_schema = request.output_schema
        current_request = request
        attempts = 0
        while True:
            try:
                payload = build_litellm_completion_payload(
                    current_request,
                )

                provider_id = client.provider_id
                
                if self._observability:
                    self._observability.record(
                        trace_id,
                        {
                            "event": "model.completion.started",
                            "model_request": payload,
                            "provider_id": provider_id,
                        },
                        "INFO",
                    )
                raw = client.completion(payload)
                if self._observability:
                    self._observability.record(
                        trace_id,
                        {
                            "event": "model.completion.raw_output",
                            "model_name": current_request.model_name,
                            "raw": raw,
                        },
                        "DEBUG",
                    )
                response = build_model_response(
                    raw,
                    request=current_request,
                    output_schema=output_schema,
                    fallback_model_name=current_request.model_name,
                    provider_id=provider_id,
                )
            except Exception as exc:  # noqa: BLE001
                fallback = ModelResponse(
                    model_name=current_request.model_name,
                    content="",
                    success=False,
                    finish_reason="error",
                    provider_id=provider_id,
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
                exhausted_raw["reason"] = "model_response_parse_failed"
                exhausted_raw["message"] += ". response parsing failed after retries"
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
                    tool_invocations=response.tool_invocations,
                    repair_reason=response.repair_reason,
                    raw=exhausted_raw,
                )
            attempts += 1
            repair_reason = response.repair_reason
            repair_message = self._build_repair_message(
                invalid_output= [tool_invocation.to_str() for tool_invocation in response.tool_invocations] \
                                if response.finish_reason == "SchemaValidationError" else response.content,
                error_text=repair_reason,
                finish_reason=response.finish_reason,
            )
            current_request = ModelRequest(
                messages=current_request.messages + (repair_message,),
                model_name=current_request.model_name,
                model_tag=current_request.model_tag,
                temperature=current_request.temperature,
                top_p=current_request.top_p,
                max_tokens=current_request.max_tokens,
                tools=current_request.tools,
                output_schema=current_request.output_schema,
                max_retries=current_request.max_retries,
                metadata=current_request.metadata,
            )
