import os
from typing import Any

try:
    import redis.asyncio as redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

from ..contracts.protocols import HotMemoryProtocol
from ..backends.in_memory import InMemoryHotMemoryStore
from ..backends.redis_store import RedisHotMemoryStore
from ..backends.jsonl_store import JSONLHotMemoryStore


def create_store(config: Any = None) -> HotMemoryProtocol:
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
    
    # 裁剪配置默认值
    max_blocks = 50
    max_tokens = 64 * 1024 #64K

    if config:
        # 兼容 QFAConfig.Memory 对象
        backend = getattr(config, "backend", None)
        redis_url = getattr(config, "redis_url", None)
        jsonl_dir = getattr(config, "jsonl_storage_dir", jsonl_dir)
        # 获取裁剪配置
        max_blocks = getattr(config, "max_blocks", max_blocks)
        max_tokens = getattr(config, "max_tokens", max_tokens)
    else:
        # 回退到环境变量
        backend = os.environ.get("STORAGE_BACKEND")
        redis_url = os.environ.get("REDIS_URL")
        # 环境变量支持裁剪配置
        env_blocks = os.environ.get("HOT_MEMORY_MAX_BLOCKS")
        if env_blocks:
            max_blocks = int(env_blocks)
        env_tokens = os.environ.get("HOT_MEMORY_MAX_TOKENS")
        if env_tokens:
            max_tokens = int(env_tokens)

    if backend == "in_memory":
        print(f"Using InMemoryHotMemoryStore (max_blocks={max_blocks}, max_tokens={max_tokens}).")
        return InMemoryHotMemoryStore(max_blocks=max_blocks, max_tokens=max_tokens)

    if backend == "jsonl":
        print(f"Using JSONLHotMemoryStore at {jsonl_dir} (max_blocks={max_blocks}, max_tokens={max_tokens}).")
        return JSONLHotMemoryStore(base_dir=jsonl_dir, max_blocks=max_blocks, max_tokens=max_tokens)

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
                print(f"Connected to Redis at {resolved_url}. Using RedisHotMemoryStore (max_blocks={max_blocks}, max_tokens={max_tokens}).")
                return RedisHotMemoryStore(client, max_blocks=max_blocks, max_tokens=max_tokens)
            except Exception as e:
                if backend == "redis":
                    print(f"Redis connection failed ({e}). Falling back to JSONL.")
                else:
                    pass # 静默尝试下一个

    # 尝试 JSONL (作为 Redis 的降级或默认选项)
    try:
        print(f"Using JSONLHotMemoryStore at {jsonl_dir} (Fallback, max_blocks={max_blocks}, max_tokens={max_tokens}).")
        return JSONLHotMemoryStore(base_dir=jsonl_dir, max_blocks=max_blocks, max_tokens=max_tokens)
    except Exception as e:
        print(f"JSONL initialization failed ({e}). Falling back to InMemory.")
        return InMemoryHotMemoryStore(max_blocks=max_blocks, max_tokens=max_tokens)
