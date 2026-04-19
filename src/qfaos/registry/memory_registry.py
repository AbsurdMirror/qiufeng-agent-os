from typing import Annotated, Optional

from pydantic import validate_call, Field

from ..config import QFAConfig


class MemoryRegistry:
    """
    记忆注册表，用于管理热记忆与状态持久化的配置信息。
    """

    def __init__(self) -> None:
        """
        初始化记忆注册表。
        """
        self._config: Optional[QFAConfig.Memory] = None

    @validate_call
    def register(
        self, 
        config: Annotated[QFAConfig.Memory, Field(description="记忆配置对象")]
    ) -> None:
        """
        在注册表中记录或覆盖记忆配置。
        
        Args:
            config: 记忆配置对象。
        """
        self._config = config

    def get(self) -> Optional[QFAConfig.Memory]:
        """
        获取当前注册的记忆配置。
        
        Returns:
            Optional[QFAConfig.Memory]: 已注册的配置对象，若未注册则返回 None。
        """
        return self._config
