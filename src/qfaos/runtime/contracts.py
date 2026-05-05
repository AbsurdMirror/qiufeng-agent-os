from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from src.domain.context import JSONValue, ContextBlock
from src.domain.events import UniversalEvent
from src.domain.capabilities import CapabilityDescription
from src.domain.models import ModelMessage, ModelResponse, ParsedToolCall
from src.qfaos.config import QFAConfig
from src.qfaos.enums import QFAEnum


@dataclass(frozen=True)
class QFAEvent:
    """面向 SDK 用户暴露的统一事件对象。"""

    channel: QFAEnum.Channel
    type: QFAEnum.Event
    session_id: str
    payload: str
    raw_event: dict[str, JSONValue] = field(default_factory=dict)

    @classmethod
    def from_universal(cls, event: UniversalEvent) -> "QFAEvent":
        channel = QFAEnum.Channel.Feishu
        
        # 识别消息类型
        first_content = event.contents[0] if event.contents else None
        if first_content and first_content.type == "image":
            event_type = QFAEnum.Event.ImageMessage
            payload = first_content.file_id or ""
        else:
            event_type = QFAEnum.Event.TextMessage
            payload = event.text
            
        session_id = event.logical_uid or event.user_id
        return cls(
            channel=channel,
            type=event_type,
            session_id=session_id,
            payload=payload,
            raw_event=dict(event.raw_event),
        )


@dataclass(frozen=True)
class QFAModelOutput:
    """模型调用的结构化输出。"""

    model_response: ModelResponse
    assistant_message: ModelMessage | None
    tool_calls: tuple[ParsedToolCall, ...]

    @property
    def is_pytool_call(self) -> bool:
        return bool(self.tool_calls)

    @property
    def tool_call(self) -> ParsedToolCall | None:
        return self.tool_calls[0] if self.tool_calls else None

    @property
    def has_answer_content(self) -> bool:
        return bool(self.response_text)

    @property
    def is_answer(self) -> bool:
        return self.has_answer_content

    @property
    def response(self) -> str | None:
        return self.response_text

    @property
    def response_text(self) -> str | None:
        if self.assistant_message is not None:
            return self.assistant_message.content
        return self.model_response.content


@dataclass(frozen=True)
class QFAToolResult:
    """工具执行的结构化输出。"""

    is_ask_ticket: bool
    ticket: str | None
    tool_name: str
    tool_desc: str
    tool_args: dict[str, object]
    output: dict[str, object]
    tool_call: ParsedToolCall
    tool_message: ModelMessage

    @property
    def tool_call_id(self) -> str | None:
        return self.tool_call.call_id


class QFASessionContext(Protocol):
    """会话级上下文协议。"""

    @property
    def state(self) -> dict[str, JSONValue]:
        raise NotImplementedError

    async def get_history_blocks(self) -> tuple[ContextBlock, ...]:
        """获取当前会话的历史上下文块。"""
        raise NotImplementedError

    async def append_context_block(self, block: ContextBlock) -> None:
        """追加一个上下文块到会话历史。"""
        raise NotImplementedError

    async def set_system_prompt(self, content: str, source: str = "base_prompt") -> None:
        """设置系统提示词（如基础提示词、画像补充等），此部分不会被自动裁剪。"""
        raise NotImplementedError

    async def clear_history(self) -> None:
        """清除当前会话的所有历史记忆块。"""
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
        tool_call: ParsedToolCall,
        ticket_id: str | None = None,
    ) -> QFAToolResult:
        raise NotImplementedError

    async def send_message(self, channel: QFAEnum.Channel, text: str) -> None:
        raise NotImplementedError

    async def send_feishu_card_message(
        self,
        template_id: str,
        template_variable: dict[str, Any],
    ) -> None:
        """发送飞书卡片消息（飞书专属接口）。"""
        raise NotImplementedError

    def record(self, event_name: str, payload: dict[str, Any] | str, level: str = "INFO") -> None:
        raise NotImplementedError


class QFAExecutionContext(Protocol):
    """事件级上下文协议。"""

    def get_session_ctx(self, session_id: str) -> QFASessionContext:
        raise NotImplementedError

    def get_all_tools(self) -> list[dict[str, Any]]:
        raise NotImplementedError
