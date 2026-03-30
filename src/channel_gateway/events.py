from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UniversalEventContent:
    """
    事件内容块 (Event Content Block)。
    
    设计意图：
    为了支持未来多模态消息（如文本、图片、文件混排）而设计的原子内容单元。
    
    Attributes:
        type (str): 内容类型标识，例如 "text", "image", "file"。
        data (str): 文本内容载荷。对于图片或文件可能为空或为辅助描述。
        file_id (str | None): 渠道方（如飞书）提供的文件或图片唯一标识，用于后续介质下载。默认为 None。
    """
    type: str
    data: str
    file_id: str | None = None


@dataclass(frozen=True)
class UniversalEvent:
    """
    系统内部统一的事件防腐层模型 (Universal Event Model)。
    
    设计意图：
    隔离外部渠道（如飞书、钉钉、微信）的异构数据结构。无论外部消息格式多复杂，
    进入编排引擎前均会被解析器归一化为本数据结构。
    
    Attributes:
        event_id (str): 平台下发的全局唯一事件标识。
        timestamp (int): 事件发生的毫秒级时间戳。
        platform_type (str): 来源平台标识，例如 "feishu"。
        user_id (str): 发送者的平台级用户 ID（如飞书的 open_id）。
        group_id (str | None): 所在群聊 ID（如果为群消息）。
        room_id (str | None): 所在房间 ID。
        message_id (str): 渠道方返回的原始消息 ID，用于会话回复与引用。
        contents (tuple[UniversalEventContent, ...]): 消息内容块元组，支持富文本/多模态内容组合。
        raw_event (dict[str, Any]): 原始事件字典快照，用于 Debug 和兜底排查。
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
    logical_uid: str | None = None # 添加用于T4阶段身份映射的字段

    @property
    def text(self) -> str:
        """
        向后兼容属性：快速提取事件中的首个文本内容。
        在 P0 阶段主要处理纯文本消息时非常有用，允许现有代码通过 event.text 直接获取文本。
        
        Returns:
            str: 提取的文本数据，若无则返回空字符串。
        """
        for content in self.contents:
            if content.type == "text":
                return content.data
        return ""


# 别名映射，确保兼容上层尚未重构的遗留代码（例如旧版编排层直接 import UniversalTextEvent）
UniversalTextEvent = UniversalEvent

