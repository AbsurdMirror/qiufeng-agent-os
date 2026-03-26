from src.model_provider.contracts import (
    InMemoryModelProviderClient,
    ModelProviderClient,
    ModelRequest,
    ModelResponse,
)
from src.model_provider.exports import ModelProviderExports


def initialize() -> ModelProviderExports:
    client = InMemoryModelProviderClient()
    return ModelProviderExports(
        layer="model_provider",
        status="initialized",
        client=client,
        invoke_sync=lambda request: _invoke_sync(client=client, request=request),
    )


def _invoke_sync(client: ModelProviderClient, request: ModelRequest) -> ModelResponse:
    return client.invoke(request)
