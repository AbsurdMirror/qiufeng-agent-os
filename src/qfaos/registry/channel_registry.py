from typing import Dict, List, Annotated

from pydantic import validate_call, Field

from ..enums import QFAEnum
from ..config import QFAConfig

class ChannelRegistry:
    """
    渠道注册表，用于集中管理所有渠道的配置信息。
    """

    def __init__(self):
        """
        初始化注册表。
        """
        self._channels: Dict[QFAEnum.Channel, QFAConfig.ChannelConfigUnion] = {}

    @validate_call
    def register(
        self,
        channel_type: Annotated[QFAEnum.Channel, Field(description="渠道类型")],
        config: Annotated[QFAConfig.ChannelConfigUnion, Field(description="渠道对应的配置")]
    ) -> None:
        """
        在注册表中记录或覆盖一个渠道的配置。
        
        Args:
            channel_type: 渠道标识符。
            config: 渠道配置对象。
        """
        self._channels[channel_type] = config

    @validate_call
    def get(
        self,
        channel_type: Annotated[QFAEnum.Channel, Field(description="渠道类型")]
    ) -> QFAConfig.ChannelConfigUnion | None:
        """
        根据渠道类型获取对应的配置。
        
        Args:
            channel_type: 渠道标识符。
            
        Returns:
            QFAConfig.ChannelConfigUnion | None: 已注册的配置对象，若未注册则返回 None。
        """
        return self._channels.get(channel_type)

    def list_channels(self) -> List[QFAEnum.Channel]:
        """
        获取当前已注册的所有渠道类型列表。
        
        Returns:
            List[QFAEnum.Channel]: 已注册渠道的枚举列表。
        """
        return list(self._channels.keys())
