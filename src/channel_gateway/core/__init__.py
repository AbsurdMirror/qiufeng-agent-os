# core 子包：渠道适配层的核心运行时（NoneBot2 等框架接入）
from .nonebot_runtime import NoneBotRuntime, initialize_nonebot2

__all__ = ["NoneBotRuntime", "initialize_nonebot2"]
