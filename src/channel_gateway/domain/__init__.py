# domain 子包：渠道适配层的领域对象（事件模型、响应原语）
# 供内部实现直接引用，顶层兼容层负责对外暴露
from .events import UniversalEvent, UniversalEventContent, UniversalTextEvent, DuplicateMessageError
from .responses import ReplyPrimitive, ReplyText

__all__ = [
    "UniversalEvent",
    "UniversalEventContent",
    "UniversalTextEvent",
    "DuplicateMessageError",
    "ReplyPrimitive",
    "ReplyText",
]
