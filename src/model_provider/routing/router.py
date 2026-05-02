from typing import Annotated

from pydantic import Field

from src.domain.context import ContextBudget
from src.domain.errors import build_error_report
from src.domain.models import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
)
from src.domain.decorators import qfaos_pytool
from src.model_provider.contracts import ModelProviderClient, RawModelProviderClient
from src.model_provider.providers.litellm_adapter import (
    LiteLLMAdapter,
)
from src.model_provider.validators.output_parser import (
    ModelOutputParser,
)

from src.model_provider.input_normalizer import (
    build_context_budget,
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
        self._parser = ModelOutputParser(observability=observability)
        self._adapter = LiteLLMAdapter(observability=observability, parser=self._parser)
        
        # 自动为初始客户端注入依赖
        for client in self._clients.values():
            self._inject_dependencies(client)

    def _inject_dependencies(self, client: RawModelProviderClient) -> None:
        """为客户端注入 observability 和 adapter (如果支持)"""
        if hasattr(client, "_observability") or hasattr(client, "observability"):
            try:
                # 优先尝试 setter 注入，如果没有则直接赋值
                if hasattr(client, "set_observability"):
                    client.set_observability(self._observability)
                else:
                    client._observability = self._observability
            except Exception:
                pass
        
        if hasattr(client, "_adapter") or hasattr(client, "adapter"):
            try:
                if hasattr(client, "set_adapter"):
                    client.set_adapter(self._adapter)
                else:
                    client._adapter = self._adapter
            except Exception:
                pass

    def add_client(self, model_name: str, client: RawModelProviderClient) -> None:
        self._inject_dependencies(client)
        self._clients[model_name] = client

    def get_context_budget(self, model_name: str) -> ContextBudget:
        """获取指定模型的上下文预算配置，若未显式配置则返回默认值"""
        return build_context_budget(model_name)

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
                if self._observability:
                    self._observability.record(
                        trace_id,
                        {
                            "event": "model.completion.started",
                            "attempts": attempts,
                        },
                        "DEBUG",
                    )
                payload = self._adapter.build_litellm_completion_payload(
                    current_request,
                )
                raw = client.completion(payload)
                response, repair_error = self._adapter.build_model_response(
                    raw,
                    request=current_request,
                    output_schema=output_schema,
                    fallback_model_name=current_request.model_name,
                    provider_id=provider_id,
                    capture_repair_error=True,
                )
                if self._observability:
                    self._observability.record(
                        trace_id,
                        {
                            "event": "model.completion.done",
                            "success": response.success,
                            "repair_error": repair_error,
                        },
                        "DEBUG",
                    )
            except Exception as exc:  # noqa: BLE001
                from src.domain.errors import format_user_facing_error

                raise RuntimeError(
                    format_user_facing_error(
                        exc,
                        summary="模型调用失败",
                    )
                ) from exc

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

            attempts += 1
            if repair_error is None:
                raise RuntimeError(
                    format_user_facing_error(
                        exc,
                        summary="模型响应解析失败但是没有repair_error",
                    )
                ) from exc
            repair_message = repair_error.to_repair_message()
            current_request = ModelRequest(
                messages=current_request.messages + (repair_message,),
                model_name=current_request.model_name,
                model_tag=current_request.model_tag,
                tools=current_request.tools,
                generation_config=current_request.generation_config,
                metadata=current_request.metadata,
            )
