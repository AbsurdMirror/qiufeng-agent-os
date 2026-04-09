import sys
from unittest.mock import MagicMock
sys.modules['pydantic'] = MagicMock()

import asyncio
from src.channel_gateway.responses import ReplyText, ReplyPrimitive
from src.channel_gateway.feishu_sender import FeishuAsyncSender
from src.channel_gateway.events import UniversalEvent
from src.model_provider.schema_validator import validate_and_heal, AutoHealingMaxRetriesExceeded
from src.observability_hub.cli_logger import CLILogTailer
from src.observability_hub.jsonl_storage import JSONLStorageEngine
from src.observability_hub.bootstrap import initialize as ob_init
from src.skill_hub.security import default_security_policy

print("Test passed without Pydantic crash")
