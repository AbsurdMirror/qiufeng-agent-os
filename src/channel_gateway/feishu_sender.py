import logging
from typing import Any
from src.channel_gateway.responses import ReplyText
from src.channel_gateway.events import UniversalEvent

logger = logging.getLogger(__name__)

class FeishuAsyncSender:
    """
    (GW-P0-08, GW-P0-09) 飞书异步接口与渠道适配。

    设计意图：
    提供异步回传接口以投递消息。当前阶段支持 mock 模式，不实际建立网络连接，直接将发送行为输出至日志。
    """

    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        if self.mock_mode:
            logger.info("FeishuAsyncSender initialized in mock mode.")

    async def send_text_reply(self, reply: ReplyText, target_event: UniversalEvent) -> dict[str, Any]:
        """
        向飞书投递文本回复消息。

        Args:
            reply: ReplyText 实例，纯文本响应原语
            target_event: 触发该回复的原始事件对象，用于提取目标 ID（例如 message_id, user_id）

        Returns:
            dict: 响应的 Mock 结果
        """
        payload = {
            "receive_id": target_event.user_id, # Or group_id based on event type
            "msg_type": "text",
            "content": {"text": reply.content},
            "reply_to": target_event.message_id
        }

        if self.mock_mode:
            logger.info(f"[MOCK FEISHU SEND] Payload: {payload}")
            return {"status": "success", "mock": True, "payload": payload}
        else:
            # 实际对接飞书 API 时将在这里发送 HTTP 请求
            raise NotImplementedError("Real Feishu network sending is not implemented yet.")
