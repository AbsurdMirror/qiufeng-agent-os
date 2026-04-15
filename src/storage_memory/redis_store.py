"""
P0.5 兼容性 Re-export 模块
将旧路径导入重定向到新目录结构，确保平滑迁移。
"""

from .backends.redis_store import RedisHotMemoryStore
from .factory.create_store import create_store

__all__ = [
    "RedisHotMemoryStore",
    "create_store",
]
