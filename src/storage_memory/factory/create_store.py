import os
from typing import Any

try:
    import redis.asyncio as redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

from ..contracts.protocols import HotMemoryCarrier, StorageAccessProtocol
from ..backends.in_memory import InMemoryHotMemoryStore
from ..backends.redis_store import RedisHotMemoryStore


def create_store() -> HotMemoryCarrier | StorageAccessProtocol:
    """探测环境，使用同步方式尝试连接 Redis，否则降级到内存存储"""
    if not HAS_REDIS:
        print("Redis module not installed. Falling back to InMemoryHotMemoryStore.")
        return InMemoryHotMemoryStore()

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    try:
        import redis as sync_redis
        # 使用同步探测
        sync_client = sync_redis.Redis.from_url(redis_url, decode_responses=True)
        sync_client.ping()
        sync_client.close()

        # 探测成功，挂载异步版
        client = redis.from_url(redis_url, decode_responses=True)
        print("Connected to Redis. Using RedisHotMemoryStore.")
        return RedisHotMemoryStore(client)
    except Exception as e:
        import logging
        logging.warning(f"Redis not available ({e}). Falling back to InMemoryHotMemoryStore.")
        return InMemoryHotMemoryStore()
