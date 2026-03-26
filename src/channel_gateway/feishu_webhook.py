from dataclasses import dataclass
from typing import Any, Mapping

from src.channel_gateway.event_parser import TextEventParserFactory
from src.channel_gateway.events import UniversalEvent


@dataclass(frozen=True)
class FeishuWebhookResult:
    """
    飞书 Webhook 解析结果包装类。
    用于区分当前请求是飞书开放平台的“URL验证挑战”还是真实的“业务消息事件”。
    """
    is_challenge: bool
    challenge: str | None
    event: UniversalEvent | None


def receive_feishu_webhook(payload: Mapping[str, Any]) -> FeishuWebhookResult:
    """
    处理飞书 Webhook 推送的顶级入口。
    
    Args:
        payload: 飞书通过 HTTP POST 推送过来的原始 JSON 字典
        
    Returns:
        FeishuWebhookResult: 包含解析状态和归一化事件的结果对象
    """
    # 优先处理开放平台配置 Webhook URL 时的握手验证
    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge")
        if not isinstance(challenge, str):
            raise ValueError("invalid_challenge")
        return FeishuWebhookResult(is_challenge=True, challenge=challenge, event=None)

    parser = TextEventParserFactory.get(channel="feishu", transport="webhook")
    event = parser.parse(payload)
    return FeishuWebhookResult(is_challenge=False, challenge=None, event=event)
