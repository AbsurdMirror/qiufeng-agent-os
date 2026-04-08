import logging
from typing import Any
from src.channel_gateway.responses import ReplyText
from src.channel_gateway.events import UniversalEvent

# ============================================================
# 渠道适配层 —— 飞书异步消息发送器 (Feishu Async Message Sender)
#
# 本模块实现了规格 GW-P0-08（异步接口）和 GW-P0-09（渠道适配）。
#
# 职责：
#   接收来自编排引擎的"响应原语"（如 ReplyText），将其翻译为
#   飞书开放平台 API 所需的 JSON 载荷，并通过 HTTP 异步发送。
#
# P0 阶段策略：
#   当前处于 mock 模式，不建立真实网络连接，发送行为只记录到日志中。
#   这样做的好处是：上层调用代码可以直接调用，而不需要等待真实飞书
#   环境搭建完毕，降低了开发阶段的集成门槛。
#   切换为真实模式只需将 mock_mode=False 并补全 HTTP 发送逻辑即可。
#
# 注意：本模块目前未被任何 bootstrap 文件实例化和导出，
#   是一个"已交付但未接入"的模块（详见整体审阅报告 REV-T5-CON-001）。
# ============================================================

logger = logging.getLogger(__name__)

class FeishuAsyncSender:
    """
    飞书通道的异步消息发送器 (Feishu Async Message Sender)。

    设计意图 (GW-P0-08, GW-P0-09)：
        提供异步回传接口，将渠道层的响应原语投递到飞书用户或群聊。
        当前阶段支持 mock 模式，不实际建立网络连接，直接将发送行为输出至日志，
        便于在没有飞书真实环境时进行端到端集成测试。

    Args:
        mock_mode (bool): 是否启用 mock 模式。默认为 True（安全模式）。
                          设置为 False 时，send_text_reply 将尝试真实 HTTP 发送（待实现）。

    当前限制：
        - 仅支持 ReplyText（纯文本）响应原语，尚不支持卡片、图片等富文本格式。
        - 飞书 API 必需字段 receive_id_type 尚未包含在 payload 中，
          切换到真实模式前必须补全（详见审阅报告）。

    使用示例：
        >>> sender = FeishuAsyncSender(mock_mode=True)
        >>> reply = ReplyText(content="Hello, World!")
        >>> result = await sender.send_text_reply(reply, target_event)
    """

    def __init__(self, mock_mode: bool = True):
        # mock_mode=True：所有"发送"操作只记录日志，不产生真实网络请求
        self.mock_mode = mock_mode
        if self.mock_mode:
            logger.info("FeishuAsyncSender initialized in mock mode.")

    async def send_text_reply(self, reply: ReplyText, target_event: UniversalEvent) -> dict[str, Any]:
        """
        向飞书投递纯文本回复消息（异步）。

        Args:
            reply (ReplyText): 纯文本响应原语，包含要发送的文本内容。
            target_event (UniversalEvent): 触发本次回复的原始事件。
                用于从中提取收件目标（user_id / message_id），
                确保回复精准发送给原始发言人，并关联到原始消息线程。

        Returns:
            dict[str, Any]: mock 模式下返回模拟的成功响应字典；
                            真实模式下应返回飞书 API 的 HTTP 响应体（待实现）。

        Raises:
            NotImplementedError: 当 mock_mode=False 时抛出，提示真实发送逻辑尚未实现。

        风险提示：
            当前 payload 缺少飞书必需字段 receive_id_type（如 "open_id"），
            真实模式下调用飞书 API 将会报错。详见审阅报告 [REV-GW0809-BUG-001]。
        """
        # 构造向飞书发送的消息载荷
        # receive_id: 收件人 ID，这里使用事件发送者的 user_id 作为回复目标
        # TODO: 群聊场景应使用 target_event.group_id 而非 user_id
        # TODO: 真实飞书 API 还需要额外传入 receive_id_type 字段（如 "open_id"）
        payload = {
            "receive_id": target_event.user_id,  # 注意：群聊时应改用 group_id，详见审阅报告
            "msg_type": "text",                   # 消息类型固定为纯文本
            "content": {"text": reply.content},   # 真正的文本内容，来自响应原语
            "reply_to": target_event.message_id   # 关联原消息 ID，飞书将以回复线程形式展示
        }

        if self.mock_mode:
            # mock 模式：不发送真实请求，直接打印 payload 到日志，方便开发调试
            logger.info(f"[MOCK FEISHU SEND] Payload: {payload}")
            return {"status": "success", "mock": True, "payload": payload}
        else:
            # 真实模式：此处应使用 httpx 或 aiohttp 向飞书开放平台发送 HTTP POST 请求
            # 飞书发送消息 API: POST https://open.feishu.cn/open-apis/im/v1/messages
            raise NotImplementedError("Real Feishu network sending is not implemented yet.")

