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
