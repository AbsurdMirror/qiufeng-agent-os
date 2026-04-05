from dataclasses import dataclass

@dataclass(frozen=True)
class ReplyText:
    """
    纯文本响应标准 (Text Reply Primitive)。

    设计意图：
    (GW-P0-07) 为渠道层提供统一的纯文本回复结构，屏蔽不同渠道下发消息时的结构差异。
    """
    content: str
