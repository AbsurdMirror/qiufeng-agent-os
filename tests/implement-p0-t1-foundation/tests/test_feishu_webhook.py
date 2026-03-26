import pytest
import json
from src.channel_gateway.feishu_webhook import (
    receive_feishu_webhook,
    FeishuWebhookResult
)
from src.channel_gateway.events import UniversalTextEvent

def test_cg_01_url_verification():
    """测试项 CG-01: 处理飞书 URL 验证挑战"""
    payload = {
        "type": "url_verification",
        "challenge": "challenge_string_123"
    }
    result = receive_feishu_webhook(payload)
    assert result.is_challenge is True
    assert result.challenge == "challenge_string_123"
    assert result.event is None
