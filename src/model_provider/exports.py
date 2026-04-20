from collections.abc import Callable
from dataclasses import dataclass

from src.domain.models import ModelRequest, ModelResponse
from src.model_provider.contracts import ModelProviderClient


@dataclass(frozen=True)
class ModelProviderExports:
    """
    模型抽象层的强类型模块导出容器。
    
    遵守 P0 T1 阶段制定的“强类型模块导出规范”，避免使用 `dict[str, Any]`。
    """
    layer: str
    status: str
    client: ModelProviderClient
    invoke_sync: Callable[[ModelRequest], ModelResponse]
