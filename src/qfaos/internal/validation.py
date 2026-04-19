from typing import Annotated

from pydantic import validate_call, Field

from ..config import QFAConfig
from ..enums import QFAEnum
from ..errors import QFAInvalidConfigError


@validate_call
def validate_feishu_mode_requirements(
    config: Annotated[QFAConfig.Channel.Feishu, Field(description="飞书渠道配置")]
) -> None:
    """
    针对飞书运行模式进行业务逻辑校验。
    
    例如：当模式为 Webhook 时，必须提供校验 Token 和加密 Key。
    
    Args:
        config: 飞书渠道配置对象。
        
    Raises:
        QFAInvalidConfigError: 当 Webhook 模式下缺少必要参数时抛出。
    """
    if config.mode == QFAEnum.Feishu.Mode.webhook:
        if not config.verify_token:
            raise QFAInvalidConfigError("当飞书运行在 Webhook 模式时，必须提供 verify_token")
        if not config.encrypt_key:
            raise QFAInvalidConfigError("当飞书运行在 Webhook 模式时，必须提供 encrypt_key")
