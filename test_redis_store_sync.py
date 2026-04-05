import asyncio
from src.storage_memory.bootstrap import initialize
from src.storage_memory.contracts import HotMemoryItem

def test_sync_init():
    exports = initialize()
    # It should connect to Redis because we aren't in a running event loop here
    print("Sync init successful!")

test_sync_init()
