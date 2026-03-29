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
    """
    模型请求的路由分发器。

    设计意图：
    将所有的模型客户端（目前有内存模拟和 MiniMax）组合在一起，
    像一个“接线员”一样，根据请求中的元数据特征，将请求智能路由给对应的真实客户端去处理。
    这使得上层（编排层）只需要面对这一个路由客户端，而不需要知道底层到底有多少种模型供应商。
    """
    def __init__(
        self,
        *,
        default_client: ModelProviderClient,
        minimax_client: ModelProviderClient,
    ) -> None:
        self._default_client = default_client
        self._minimax_client = minimax_client

    def invoke(self, request: ModelRequest) -> ModelResponse:
        # 如果请求被识别为发给 MiniMax 的，则转发给 minimax_client 处理
        if is_minimax_request(request):
            return self._minimax_client.invoke(request)
        # 否则兜底使用默认的客户端（目前是内存模拟器）处理
        return self._default_client.invoke(request)
