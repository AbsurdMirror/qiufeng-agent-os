from src.model_provider.contracts import (
    InMemoryModelProviderClient,
    ModelProviderClient,
    ModelRequest,
    ModelResponse,
)
from src.model_provider.exports import ModelProviderExports
from src.model_provider.minimax import MiniMaxModelProviderClient, is_minimax_request


def initialize() -> ModelProviderExports:
    """
    模型抽象层 (Model Provider) 的初始化引导函数。
    
    此函数会被 `src.app.bootstrap` 在应用启动时调用。它负责：
    初始化底层的模型客户端，并暴露代理方法供编排引擎调用。
    当前提供最小可用的路由客户端：默认走内存模拟客户端，
    当请求显式指定 MiniMax 模型或路由标识时切换到 MiniMax 适配器。
    """
    client = RoutedModelProviderClient(
        default_client=InMemoryModelProviderClient(),
        minimax_client=MiniMaxModelProviderClient(),
    )
    return ModelProviderExports(
        layer="model_provider",
        status="initialized",
        client=client,
        invoke_sync=lambda request: _invoke_sync(client=client, request=request),
    )


def _invoke_sync(client: ModelProviderClient, request: ModelRequest) -> ModelResponse:
    """包装代理：通过客户端发起同步推理请求"""
    return client.invoke(request)


class RoutedModelProviderClient:
    def __init__(
        self,
        *,
        default_client: ModelProviderClient,
        minimax_client: ModelProviderClient,
    ) -> None:
        self._default_client = default_client
        self._minimax_client = minimax_client

    def invoke(self, request: ModelRequest) -> ModelResponse:
        if is_minimax_request(request):
            return self._minimax_client.invoke(request)
        return self._default_client.invoke(request)
