"""
model_provider.routing —— 模型路由器实现。

当前内置：
- router: ModelRouter，基于显式名称匹配与上下文裁剪的路由调度器
"""
from .router import ModelRouter

__all__ = [
    "ModelRouter",
]
