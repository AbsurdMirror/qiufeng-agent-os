from typing import Any, Literal

from src.channel_gateway.core.domain.events import UniversalEvent
from src.channel_gateway.core.domain.responses import ReplyText
from src.channel_gateway.exports import ChannelGatewayExports
from src.observability_hub.exports import ObservabilityHubExports
from src.orchestration_engine.context.runtime_context import RuntimeContext
from src.model_provider.contracts import ModelMessage
from src.orchestration_engine.contracts import (
    CapabilityDescription,
    CapabilityHub,
    CapabilityRequest,
    CapabilityResult,
)
from src.qfaos.config import QFAConfig
from src.qfaos.enums import QFAEnum
from src.qfaos.errors import QFAInvalidConfigError
from src.qfaos.runtime.contracts import (
    QFAExecutionContext,
    QFAModelOutput,
    QFASessionContext,
    QFAToolResult,
)
from src.storage_memory.contracts.models import HotMemoryItem
from src.storage_memory.exports import StorageMemoryExports

from ..internal.primitives import reset_approved_ticket_id, set_approved_ticket_id


class DefaultQFASessionContext(QFASessionContext):
    """T7.7 默认会话上下文实现。"""

    def __init__(
        self,
        *,
        runtime_context: RuntimeContext,
        capability_hub: CapabilityHub,
        storage_memory: StorageMemoryExports,
        logic_id: str,
        event: UniversalEvent,
        channel_gateway: ChannelGatewayExports | None,
        observability: ObservabilityHubExports | None,
    ) -> None:
        self._runtime_context = runtime_context
        self._capability_hub = capability_hub
        self._storage_memory = storage_memory
        self._logic_id = logic_id
        self._event = event
        self._channel_gateway = channel_gateway
        self._observability = observability

    @property
    def state(self) -> dict[str, Any]:
        return self._runtime_context.state

    async def get_memory(self) -> list[dict[str, Any]]:
        history = self._runtime_context.memory.get("dialogue_history", [])
        if not isinstance(history, list):
            return []
        return [dict(item) for item in history if isinstance(item, dict)]

    async def add_memory(self, content: str) -> None:
        item = HotMemoryItem(
            trace_id=self._runtime_context.trace_id,
            role="assistant",
            content=content,
        )
        await self._storage_memory.append_hot_memory(
            self._logic_id,
            self._runtime_context.session_id,
            item,
            10,
        )
        dialogue = self._runtime_context.memory.setdefault("dialogue_history", [])
        if isinstance(dialogue, list):
            dialogue.append({"role": "assistant", "content": content})

    async def model_ask(
        self,
        model: QFAConfig.ModelConfigUnion,
        prompt: str,
        tools_mode: Literal["none", "all", "custom"] = "all",
        tools: tuple[CapabilityDescription, ...] | None = None,
    ) -> QFAModelOutput:
        model_name = model.model_name
        if tools_mode == "none":
            selected_tools: tuple[CapabilityDescription, ...] = ()
        elif tools_mode == "custom":
            if tools is None:
                raise QFAInvalidConfigError("tools_mode='custom' 时必须传入 tools")
            selected_tools = tools
        else:
            selected_tools = tuple(
                capability
                for capability in self._capability_hub.list_capabilities()
                if capability.domain == "tool"
            )
        messages = self._build_messages(prompt)
        result = await self._capability_hub.invoke(
            CapabilityRequest(
                capability_id="model.chat.default",
                payload={
                    "messages": messages,
                    "model_name": model_name,
                    "tools": selected_tools
                },
                metadata={"trace_id": self._runtime_context.trace_id},
            )
        )
        return self._to_model_output(result)

    async def call_pytool(
        self,
        tool_call: dict[str, Any],
        ticket_id: str | None = None,
    ) -> QFAToolResult:
        capability_id = tool_call.get("capability_id")
        if not isinstance(capability_id, str) or not capability_id.strip():
            raise QFAInvalidConfigError("tool_call.capability_id 必须为非空字符串")
        tool_args = tool_call.get("payload", {})
        if not isinstance(tool_args, dict):
            raise QFAInvalidConfigError("tool_call.payload 必须为 dict")
        tool_metadata = tool_call.get("metadata", {})
        if not isinstance(tool_metadata, dict):
            raise QFAInvalidConfigError("tool_call.metadata 必须为 dict")
        token = set_approved_ticket_id(ticket_id)
        try:
            result = await self._capability_hub.invoke(
                CapabilityRequest(
                    capability_id=capability_id,
                    payload=tool_args,
                    metadata={**tool_metadata, "trace_id": self._runtime_context.trace_id},
                    ticket_id=ticket_id,
                )
            )
        finally:
            reset_approved_ticket_id(token)
        return self._to_tool_result(capability_id, tool_args, result)

    async def send_message(self, channel: QFAEnum.Channel, text: str) -> None:
        if channel != QFAEnum.Channel.Feishu:
            raise QFAInvalidConfigError(f"当前仅支持飞书消息发送，收到: {channel}")
        if self._channel_gateway is None:
            raise QFAInvalidConfigError("当前上下文未注入 Channel Gateway，无法发送消息")
        await self._channel_gateway.feishu_sender.send_text_reply(
            ReplyText(content=text),
            self._event,
        )

    def record(self, event_name: str, payload: dict[str, Any] | str, level: str = "info") -> None:
        if self._observability is None:
            return
        record = self._observability.record(
            self._runtime_context.trace_id,
            {"event": event_name, "payload": payload},
            level,
        )
        self._observability.jsonl_storage.write_record(record)

    def _to_model_output(self, result: CapabilityResult) -> QFAModelOutput:
        if not result.success:
            return QFAModelOutput(
                is_pytool_call=False,
                tool_call=None,
                is_answer=True,
                response=result.error_message or "",
            )
        output = result.output
        print("DEBUG",
            f"_to_model_output: result.output={output}"
        )
        tool_calls = output.get("tool_calls", [])
        if isinstance(tool_calls, tuple) and tool_calls:
            first = tool_calls[0]
            tool_call = first if isinstance(first, dict) else None
        else:
            tool_call = None
        if tool_call:
            return QFAModelOutput(
                is_pytool_call=True,
                tool_call=tool_call,
                is_answer=False,
                response=None,
            )
        content = output.get("content")
        return QFAModelOutput(
            is_pytool_call=False,
            tool_call=None,
            is_answer=True,
            response=str(content) if content is not None else "",
        )

    def _to_tool_result(
        self,
        capability_id: str,
        tool_args: dict[str, Any],
        result: CapabilityResult,
    ) -> QFAToolResult:
        capability = self._capability_hub.get_capability(capability_id)
        tool_desc = capability.description if capability else ""
        if not result.success and result.error_code == "requires_user_approval":
            ticket = result.metadata.get("ticket_id")
            return QFAToolResult(
                is_ask_ticket=True,
                ticket=str(ticket) if ticket else None,
                tool_name=capability_id,
                tool_desc=tool_desc,
                tool_args=tool_args,
                output=dict(result.output),
            )
        return QFAToolResult(
            is_ask_ticket=False,
            ticket=None,
            tool_name=capability_id,
            tool_desc=tool_desc,
            tool_args=tool_args,
            output=dict(result.output),
        )

    def _build_messages(self, prompt: str) -> tuple[ModelMessage, ...]:
        history = self._runtime_context.memory.get("dialogue_history", [])
        messages: list[ModelMessage] = []
        if isinstance(history, list):
            for item in history:
                if not isinstance(item, dict):
                    continue
                role = item.get("role")
                content = item.get("content")
                if isinstance(role, str) and isinstance(content, str):
                    messages.append(ModelMessage(role=role, content=content))
        messages.append(ModelMessage(role="user", content=prompt))
        return tuple(messages)


class DefaultQFAExecutionContext(QFAExecutionContext):
    """T7.7 事件级上下文实现。"""

    def __init__(
        self,
        *,
        session_ctx: DefaultQFASessionContext,
        capability_hub: CapabilityHub,
    ) -> None:
        self._session_ctx = session_ctx
        self._capability_hub = capability_hub

    def get_session_ctx(self, session_id: str) -> QFASessionContext:
        _ = session_id
        return self._session_ctx

    def get_all_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for capability in self._capability_hub.list_capabilities():
            if capability.domain != "tool":
                continue
            tools.append(
                {
                    "name": capability.name,
                    "capability_id": capability.capability_id,
                    "description": capability.description,
                    "input_schema": dict(capability.input_schema),
                }
            )
        return tools
