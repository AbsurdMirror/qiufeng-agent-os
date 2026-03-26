from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UniversalEventContent:
    """
    事件内容块。
    支持多模态内容（如文本、图片、文件）。
    对于纯文本，type="text"，data 为文本内容。
    对于图片或文件，type="image"|"file"，file_id 存储渠道方的文件标识。
    """
    type: str
    data: str
    file_id: str | None = None


@dataclass(frozen=True)
class UniversalEvent:
    """
    系统内部统一的事件数据模型。
    无论消息是来自飞书长连接、飞书 Webhook 还是未来其他平台，
    最终都会被归一化为这个结构，供编排引擎 (Orchestration Engine) 使用。
    支持多模态内容（contents 数组）。
    """
    event_id: str
    timestamp: int
    platform_type: str
    user_id: str
    group_id: str | None
    room_id: str | None
    message_id: str
    contents: tuple[UniversalEventContent, ...]
    raw_event: dict[str, Any]

    @property
    def text(self) -> str:
        """
        向后兼容属性：快速提取事件中的首个文本内容。
        在 P0 阶段主要处理纯文本消息时非常有用。
        """
        for content in self.contents:
            if content.type == "text":
                return content.data
        return ""


# 别名映射，确保兼容上层尚未重构的遗留代码（如有）
UniversalTextEvent = UniversalEvent

