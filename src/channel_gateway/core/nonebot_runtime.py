from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NoneBotRuntime:
    """
    NoneBot2 运行时状态的数据模型。
    用于在应用启动时安全地包装 NoneBot 框架的初始化结果。
    
    Attributes:
        framework: 框架名称，固定为 "nonebot2"
        initialized: 框架是否成功初始化
        driver_name: 底层驱动名称（如 FastAPI、Quart 等），未安装时为 None
        error: 初始化失败时的错误信息
        driver: NoneBot 的 Driver 实例引用，用于后续挂载路由或生命周期
    """
    framework: str
    initialized: bool
    driver_name: str | None
    error: str | None
    driver: Any | None


def initialize_nonebot2(host: str, port: int) -> NoneBotRuntime:
    """
    尝试初始化 NoneBot2 框架。
    
    采用防御性编程：如果未安装 nonebot 库或初始化失败，
    不会抛出致命异常导致进程崩溃，而是返回一个包含错误信息的 NoneBotRuntime 对象。
    这种设计允许应用在没有安装机器人框架的环境下（例如仅运行轻量级工具时）继续生存。
    
    Args:
        host: 监听的 IP 地址
        port: 监听的端口
        
    Returns:
        NoneBotRuntime: 包含初始化状态的不可变对象
    """
    try:
        import nonebot
    except ImportError:
        return NoneBotRuntime(
            framework="nonebot2",
            initialized=False,
            driver_name=None,
            error="nonebot2_not_installed",
            driver=None,
        )

    try:
        # 执行 NoneBot 框架的全局初始化
        nonebot.init(host=host, port=port)
        driver = nonebot.get_driver()
        return NoneBotRuntime(
            framework="nonebot2",
            initialized=True,
            driver_name=driver.__class__.__name__,
            error=None,
            driver=driver,
        )
    except Exception as error:
        return NoneBotRuntime(
            framework="nonebot2",
            initialized=False,
            driver_name=None,
            error=str(error),
            driver=None,
        )
