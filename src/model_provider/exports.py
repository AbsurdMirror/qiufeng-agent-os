from collections.abc import Callable
from dataclasses import dataclass

from src.model_provider.contracts import ModelProviderClient, ModelRequest, ModelResponse


@dataclass(frozen=True)
class ModelProviderExports:
    layer: str
    status: str
    client: ModelProviderClient
    invoke_sync: Callable[[ModelRequest], ModelResponse]
