from typing import Annotated

from pydantic import Field

from src.domain.errors import build_error_report
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
        provider_id = client.provider_id
        while True:
            try:
                payload = build_litellm_completion_payload(
                    current_request,
                )
                
                if self._observability:
                    self._observability.record(
                        trace_id,
                        {
                            "event": "model.completion.started",
                            "model_request": payload,
                            "provider_id": provider_id,
                        },
                        "DEBUG",
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
                response, repair_error = build_model_response(
                    raw,
                    request=current_request,
                    output_schema=output_schema,
                    fallback_model_name=current_request.model_name,
                    provider_id=provider_id,
                    capture_repair_error=True,
                )
            except Exception as exc:  # noqa: BLE001
                fallback = ModelResponse(
                    model_name=current_request.model_name,
                    content="",
                    success=False,
                    finish_reason="error",
                    provider_id=provider_id,
                    raw={
                        "reason": "model_router_completion_failed",
                        "message": build_error_report(
                            exc,
                            summary="模型调用失败",
                        ).to_user_message(),
                    },
                )
                response = fallback
                repair_error = None

            if response.success:
                return response

            if attempts >= max_retries:
                exhausted_raw = dict(response.raw)
                exhausted_raw["reason"] = "model_response_parse_failed"
                current_message = exhausted_raw.get("message")
                if isinstance(current_message, str):
                    exhausted_raw["message"] = f"{current_message}\nresponse parsing failed after retries"
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
                    message=response.message,
                    repair_reason=response.repair_reason,
                    raw=exhausted_raw,
                )
            if repair_error is None:
                return ModelResponse(
                    model_name=response.model_name,
                    content=response.content,
                    success=response.success,
                    finish_reason=response.finish_reason,
                    provider_id=response.provider_id,
                    usage=response.usage,
                    parsed=response.parsed,
                    tool_calls=response.tool_calls,
                    message=response.message,
                    repair_reason=response.repair_reason,
                    raw=response.raw,
                )
            attempts += 1
            repair_message = repair_error.to_repair_message()
            current_request = ModelRequest(
                messages=current_request.messages + (repair_message,),
                model_name=current_request.model_name,
                model_tag=current_request.model_tag,
                tools=current_request.tools,
                generation_config=current_request.generation_config,
                metadata=current_request.metadata,
            )
