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
from ..backends.jsonl_store import JSONLHotMemoryStore


def create_store(redis_url: str | None = None) -> HotMemoryCarrier | StorageAccessProtocol:
    """探测环境，使用同步方式尝试连接 Redis，否则降级到 JSONL 存储或内存存储"""
    backend_type = os.environ.get("STORAGE_BACKEND", "").lower()

    if backend_type == "memory":
        print("Using InMemoryHotMemoryStore.")
        return InMemoryHotMemoryStore()

    if backend_type == "jsonl":
        storage_dir = os.environ.get("JSONL_STORAGE_DIR", ".storage")
        print(f"Using JSONLHotMemoryStore at {storage_dir}.")
        return JSONLHotMemoryStore(base_dir=storage_dir)

    # 默认逻辑：优先尝试 Redis
    if HAS_REDIS:
        resolved_redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379")
        try:
            import redis as sync_redis
            # 使用同步探测
            sync_client = sync_redis.Redis.from_url(resolved_redis_url, decode_responses=True)
            sync_client.ping()
            sync_client.close()

            # 探测成功，挂载异步版
            client = redis.from_url(resolved_redis_url, decode_responses=True)
            print("Connected to Redis. Using RedisHotMemoryStore.")
            return RedisHotMemoryStore(client)
        except Exception as e:
            import logging
            logging.warning(f"Redis not available ({e}). Falling back to JSONLHotMemoryStore.")

    # 最后的降级方案：JSONL (比内存更可靠，因为它持久化)
    storage_dir = os.environ.get("JSONL_STORAGE_DIR", ".storage")
    print(f"Falling back to JSONLHotMemoryStore at {storage_dir}.")
    return JSONLHotMemoryStore(base_dir=storage_dir)
