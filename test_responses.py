import sys
from unittest.mock import MagicMock
sys.modules['pydantic'] = MagicMock()

from src.channel_gateway.responses import ReplyText

try:
    print("Normal length test:", ReplyText(content='a').content)
    print("Truncation test length:", len(ReplyText(content='a'*5000).content))
    ReplyText(content='')
except ValueError as e:
    print("Empty string test caught expected error:", e)
