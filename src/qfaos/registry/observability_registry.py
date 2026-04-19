from typing import Annotated, Optional

from pydantic import validate_call, Field

from ..config import QFAConfig


class ObservabilityRegistry:
    """
    观测注册表，用于管理日志落盘（JSONL）等可观测性配置。
    """

    def __init__(self) -> None:
        """
        初始化观测注册表。
        """
        self._log_config: Optional[QFAConfig.Observability.Log] = None

    @validate_call
    def register_log(
        self, 
        config: Annotated[QFAConfig.Observability.Log, Field(description="日志观测配置对象")]
    ) -> None:
        """
        在注册表中记录或覆盖日志观测配置。
        
        Args:
            config: 日志配置对象。
        """
        self._log_config = config

    def get_log(self) -> Optional[QFAConfig.Observability.Log]:
        """
        获取当前注册的日志观测配置。
        
        Returns:
            Optional[QFAConfig.Observability.Log]: 已注册的配置对象，若未注册则返回 None。
        """
        return self._log_config
