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


def create_store(config: Any = None) -> HotMemoryCarrier | StorageAccessProtocol:
    """
    根据配置创建存储后端，支持自动降级。
    
    降级策略：
    1. 显式指定 memory -> InMemory
    2. 显式指定 jsonl -> JSONL
    3. 显式指定 redis -> 尝试 Redis，失败则降级到 JSONL
    4. 未指定 -> 尝试 Redis -> 尝试 JSONL -> 降级到 InMemory
    """
    backend = None
    redis_url = None
    jsonl_dir = os.environ.get("JSONL_STORAGE_DIR", ".storage")

    if config:
        # 兼容 QFAConfig.Memory 对象
        backend = getattr(config, "backend", None)
        redis_url = getattr(config, "redis_url", None)
        jsonl_dir = getattr(config, "jsonl_storage_dir", jsonl_dir)
    else:
        # 回退到环境变量
        backend = os.environ.get("STORAGE_BACKEND")
        redis_url = os.environ.get("REDIS_URL")

    if backend == "in_memory":
        print("Using InMemoryHotMemoryStore.")
        return InMemoryHotMemoryStore()

    if backend == "jsonl":
        print(f"Using JSONLHotMemoryStore at {jsonl_dir}.")
        return JSONLHotMemoryStore(base_dir=jsonl_dir)

    # 尝试 Redis (如果显式指定 redis 或未指定)
    if backend == "redis" or backend is None:
        if HAS_REDIS:
            resolved_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379")
            try:
                import redis as sync_redis
                sync_client = sync_redis.Redis.from_url(resolved_url, decode_responses=True)
                sync_client.ping()
                sync_client.close()

                client = redis.from_url(resolved_url, decode_responses=True)
                print(f"Connected to Redis at {resolved_url}. Using RedisHotMemoryStore.")
                return RedisHotMemoryStore(client)
            except Exception as e:
                if backend == "redis":
                    print(f"Redis connection failed ({e}). Falling back to JSONL.")
                else:
                    pass # 静默尝试下一个

    # 尝试 JSONL (作为 Redis 的降级或默认选项)
    try:
        print(f"Using JSONLHotMemoryStore at {jsonl_dir} (Fallback).")
        return JSONLHotMemoryStore(base_dir=jsonl_dir)
    except Exception as e:
        print(f"JSONL initialization failed ({e}). Falling back to InMemory.")
        return InMemoryHotMemoryStore()
