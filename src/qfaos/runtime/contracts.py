from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from src.channel_gateway.core.domain.events import UniversalEvent
from src.orchestration_engine.contracts import CapabilityDescription
from src.qfaos.config import QFAConfig
from src.qfaos.enums import QFAEnum


@dataclass(frozen=True)
class QFAEvent:
    """面向 SDK 用户暴露的统一事件对象。"""

    channel: QFAEnum.Channel
    type: QFAEnum.Event
    session_id: str
    payload: str
    raw_event: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_universal(cls, event: UniversalEvent) -> "QFAEvent":
        channel = QFAEnum.Channel.Feishu
        event_type = QFAEnum.Event.TextMessage
        session_id = event.logical_uid or event.user_id
        return cls(
            channel=channel,
            type=event_type,
            session_id=session_id,
            payload=event.text,
            raw_event=dict(event.raw_event),
        )


@dataclass(frozen=True)
class QFAModelOutput:
    """模型调用的结构化输出。"""

    is_pytool_call: bool
    tool_call: dict[str, Any] | None
    is_answer: bool
    response: str | None


@dataclass(frozen=True)
class QFAToolResult:
    """工具执行的结构化输出。"""

    is_ask_ticket: bool
    ticket: str | None
    tool_name: str
    tool_desc: str
    tool_args: dict[str, Any]
    output: dict[str, Any]


class QFASessionContext(Protocol):
    """会话级上下文协议。"""

    @property
    def state(self) -> dict[str, Any]:
        raise NotImplementedError

    async def get_memory(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def add_memory(self, content: str) -> None:
        raise NotImplementedError

    async def model_ask(
        self,
        model: QFAConfig.ModelConfigUnion,
        prompt: str,
        tools_mode: Literal["none", "all", "custom"] = "all",
        tools: tuple[CapabilityDescription, ...] | None = None,
    ) -> QFAModelOutput:
        raise NotImplementedError

    async def call_pytool(
        self,
        tool_call: dict[str, Any],
        ticket_id: str | None = None,
    ) -> QFAToolResult:
        raise NotImplementedError

    async def send_message(self, channel: QFAEnum.Channel, text: str) -> None:
        raise NotImplementedError

    def record(self, event_name: str, payload: dict[str, Any] | str, level: str = "info") -> None:
        raise NotImplementedError


class QFAExecutionContext(Protocol):
    """事件级上下文协议。"""

    def get_session_ctx(self, session_id: str) -> QFASessionContext:
        raise NotImplementedError

    def get_all_tools(self) -> list[dict[str, Any]]:
        raise NotImplementedError
