from src.model_provider.contracts import (
    InMemoryModelProviderClient,
    ModelProviderClient,
    ModelRequest,
    ModelResponse,
)
from src.model_provider.exports import ModelProviderExports
from src.model_provider.minimax import MiniMaxModelProviderClient, is_minimax_request


from src.model_provider.router import ModelRouter

def initialize() -> ModelProviderExports:
    """
    模型抽象层 (Model Provider) 的初始化引导函数。
    
    此函数会被 `src.app.bootstrap` 在应用启动时调用。它负责：
    初始化底层的模型客户端，并暴露代理方法供编排引擎调用。
    """
    # T4: MP-P0-01, MP-P0-02
    client = ModelRouter(
        clients={
            "default": InMemoryModelProviderClient(),
            "minimax": MiniMaxModelProviderClient()
        }
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
    [DEAD CODE WARNING - 遗留的已作废死亡代码]
    
    老的模型请求路由分发器。
    
    该类使用 if-else 与旧版 `is_minimax_request` 探测函数生造对接的方法，
    已经在本次 T4 阶段大重构时，全面由字典驱动的更高阶形态： `ModelRouter` 将其顶替与淘汰！
    请开发人员勿再调用此类，并在合适时机将这块“死亡尸斑代码”物理铲除。
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
