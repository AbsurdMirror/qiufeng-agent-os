from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UniversalTextEvent:
    event_id: str
    timestamp: int
    platform_type: str
    user_id: str
    group_id: str | None
    room_id: str | None
    message_id: str
    text: str
    raw_event: dict[str, Any]
