from dataclasses import dataclass
from typing import Protocol

# ============================================================
# 渠道适配层 —— 响应原语 (Channel Gateway Response Primitives)
#
# 本模块定义渠道层向外发送消息时使用的"响应原语"数据结构。
# 所谓"原语"，就像乐高积木中最小的标准零件——每种原语代表一种
# 最基础的消息类型（纯文本、卡片、图片等），发送器只需根据原语
# 类型决定如何投递，不需要关心内容本身的格式细节。
#
# 目前 P0 阶段只实现纯文本原语 ReplyText，未来可在此模块中
# 扩展 ReplyCard / ReplyImage 等更复杂的原语类型。
# ============================================================




class ReplyPrimitive(Protocol):
    """
    响应原语的基础协议约束 (GW-P0-07-CON-002)。

    用于统一所有响应类型的签名类型提示。
    """
    content: str

@dataclass(frozen=True)
class ReplyText(ReplyPrimitive):
    """
    纯文本响应原语 (Plain Text Reply Primitive)。

    设计意图 (GW-P0-07)：
        为渠道层提供最基础的纯文本回复结构，屏蔽不同渠道（飞书、钉钉、微信等）
        在下发文本消息时的 API 格式差异。上层编排引擎无论对接哪个渠道，
        都统一构造 ReplyText，由具体的渠道发送器（如 FeishuAsyncSender）
        在内部将其转换为各自的平台 API 载荷。

    不变性 (frozen=True)：
        使用 frozen dataclass，实例创建后不可修改，保证消息内容
        在传递过程中不会被意外篡改。

    Attributes:
        content (str): 要发送的纯文本内容字符串。
                       注意：当前没有长度或内容校验，调用方有责任
                       确保内容非空且符合目标渠道的文本长度限制。

    使用示例：
        >>> reply = ReplyText(content="任务已完成，结果如下：\\n...")
        >>> await feishu_sender.send_text_reply(reply, target_event)
    """
    # 要回复的纯文本内容。调用方应确保该字段非空，且不超过目标渠道的字符数限制。
    content: str

    def __post_init__(self):
        import logging
        logger = logging.getLogger(__name__)

        if not self.content:
            raise ValueError("ReplyText content cannot be empty.")

        if len(self.content) > 4000:
            logger.warning("ReplyText content exceeds 4000 characters. It will be truncated.")
            # Because it's a frozen dataclass, we must use object.__setattr__
            object.__setattr__(self, 'content', self.content[:4000])
