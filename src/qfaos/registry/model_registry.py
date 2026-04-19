from typing import Dict, List, Annotated

from pydantic import validate_call, Field

from ..enums import QFAEnum
from ..config import QFAConfig

class ModelRegistry:
    """
    模型注册表，用于管理所有模型服务（如 MiniMax）的配置信息。
    """

    def __init__(self):
        """
        初始化模型注册表。
        """
        self._models: Dict[QFAEnum.Model, QFAConfig.ModelConfigUnion] = {}

    @validate_call
    def register(
        self,
        model_type: Annotated[QFAEnum.Model, Field(description="模型类型枚举")],
        config: Annotated[QFAConfig.ModelConfigUnion, Field(description="对应的模型配置对象")]
    ) -> None:
        """
        在注册表中记录或覆盖一个模型的配置。
        
        Args:
            model_type: 模型标识符（如 QFAEnum.Model.MiniMax）。
            config: 模型配置对象。
        """
        self._models[model_type] = config

    @validate_call
    def get(
        self,
        model_type: Annotated[QFAEnum.Model, Field(description="模型类型枚举")]
    ) -> QFAConfig.ModelConfigUnion | None:
        """
        根据模型类型获取对应的配置。
        
        Args:
            model_type: 模型标识符。
            
        Returns:
            QFAConfig.ModelConfigUnion | None: 已注册的配置对象，若未注册则返回 None。
        """
        return self._models.get(model_type)

    def list_models(self) -> List[QFAEnum.Model]:
        """
        获取当前已注册的所有模型类型列表。
        
        Returns:
            List[QFAEnum.Model]: 已注册模型的枚举列表。
        """
        return list(self._models.keys())
