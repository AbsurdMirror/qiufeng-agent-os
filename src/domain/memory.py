from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HotMemoryItem:
    """
    单条热记忆（短期记忆）的数据载体模型。
    
    设计意图：
    用于在多轮对话中记录用户的输入、模型的输出以及工具的调用结果。
    它将被序列化后存入 Redis 的 List 结构中。
    
    Attributes:
        trace_id: 产生此条记忆的请求链路 ID。
        role: 角色标识（如 user, assistant, system）。
        content: 记忆的文本内容。
        metadata: 附加元数据（如 Token 消耗、时间戳等）。
    """
    trace_id: str
    role: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

