from dataclasses import dataclass
from typing import Any, Mapping

from src.channel_gateway.channels.feishu.text_event_parser import TextEventParserFactory
from src.domain.events import UniversalEvent


@dataclass(frozen=True)
class FeishuWebhookResult:
    """
    飞书 Webhook 解析结果包装类。
    用于区分当前请求是飞书开放平台的"URL验证挑战"还是真实的"业务消息事件"。
    """
    is_challenge: bool
    challenge: str | None
    event: UniversalEvent | None


def receive_feishu_webhook(payload: Mapping[str, Any]) -> FeishuWebhookResult:
    """
    处理飞书 Webhook 推送的顶级入口。
    
    此函数现已作为纯粹的网关门面（Facade），不再包含复杂的 JSON 嵌套解析逻辑。
    它负责拦截开放平台的挑战验证请求，若为真实业务事件，则委托给对应的 Factory Parser 进行处理。
    
    Args:
        payload: 飞书通过 HTTP POST 推送过来的原始 JSON 字典
        
    Returns:
        FeishuWebhookResult: 包含解析状态和归一化事件的防腐层结果对象
    """
    # 优先处理开放平台配置 Webhook URL 时的握手验证
    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge")
        if not isinstance(challenge, str):
            raise ValueError("invalid_challenge")
        return FeishuWebhookResult(is_challenge=True, challenge=challenge, event=None)

    # 通过策略工厂获取飞书 Webhook 的专用解析器，并将复杂解析委托给它
    parser = TextEventParserFactory.get(channel="feishu", transport="webhook")

    from src.channel_gateway.core.session.context import session_context_controller
    import dataclasses

    event = parser.parse(payload)

    # 提取完成后触发去重网关拦截
    if session_context_controller.is_duplicate(event.message_id):
        return FeishuWebhookResult(is_challenge=False, challenge=None, event=None)

    # 填充 logical_uid
    event = dataclasses.replace(event, logical_uid=session_context_controller.get_logical_uuid(event.user_id))

    return FeishuWebhookResult(is_challenge=False, challenge=None, event=event)
