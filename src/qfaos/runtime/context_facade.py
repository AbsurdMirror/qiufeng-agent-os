from typing import Any, Literal

from src.domain.events import UniversalEvent
from src.domain.responses import ReplyText, FeishuReplyCard
from src.channel_gateway.exports import ChannelGatewayExports
from src.domain.errors import format_user_facing_error
from src.observability_hub.exports import ObservabilityHubExports
from src.orchestration_engine.context.runtime_context import RuntimeContext
from src.domain.models import ModelMessage, ModelResponse
from src.domain.capabilities import CapabilityDescription, CapabilityRequest, CapabilityResult
from src.domain.translators.schema_translator import SchemaTranslator
from src.domain.translators.model_interactions import (
    ParsedToolCall,
    build_tool_result_message,
    model_message_to_debug_dict,
    model_message_to_hot_memory_item,
)
from src.orchestration_engine.contracts import CapabilityHub
from src.qfaos.config import QFAConfig
from src.qfaos.enums import QFAEnum
from src.qfaos.errors import QFAInvalidConfigError
from src.qfaos.runtime.contracts import (
    QFAExecutionContext,
    QFAModelOutput,
    QFASessionContext,
    QFAToolResult,
)
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

    async def get_memory(self) -> list[dict[str, object]]:
        history = self._runtime_context.memory.get("dialogue_history", [])
        result: list[dict[str, object]] = []
        for item in history:
            if not isinstance(item, ModelMessage):
                raise QFAInvalidConfigError("dialogue_history 中只允许存在 ModelMessage")
            result.append(model_message_to_debug_dict(item))
        return result

    async def add_memory(self, message: ModelMessage) -> None:
        item = model_message_to_hot_memory_item(message, self._runtime_context.trace_id)
        await self._storage_memory.append_hot_memory(
            self._logic_id,
            self._runtime_context.session_id,
            item,
            10,
        )
        dialogue = self._runtime_context.memory.setdefault("dialogue_history", [])
        if not isinstance(dialogue, list):
            raise QFAInvalidConfigError("dialogue_history 必须为 ModelMessage 列表")
        dialogue.append(message)

    async def add_user_text_memory(self, content: str) -> None:
        await self.add_memory(ModelMessage(role="user", content=content))

    async def add_assistant_message_memory(self, message: ModelMessage) -> None:
        if message.role != "assistant":
            raise QFAInvalidConfigError("assistant memory 必须传入 assistant 角色消息")
        await self.add_memory(message)

    async def add_tool_result_memory(self, message: ModelMessage) -> None:
        if message.role != "tool":
            raise QFAInvalidConfigError("tool result memory 必须传入 tool 角色消息")
        await self.add_memory(message)

    async def clear_memory(self) -> None:
        # 1. 清除持久化存储中的热记忆
        await self._storage_memory.delete_hot_memory(
            self._logic_id,
            self._runtime_context.session_id,
        )
        # 2. 清除当前运行时的对话历史快照
        if "dialogue_history" in self._runtime_context.memory:
            self._runtime_context.memory["dialogue_history"] = []

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
                capability_id="model.completion",
                payload={
                    "request": {
                        "messages": messages,
                        "model_name": model_name,
                        "tools": selected_tools
                    }
                },
                metadata={"trace_id": self._runtime_context.trace_id},
            )
        )
        return self._to_model_output(result)

    async def call_pytool(
        self,
        tool_call: ParsedToolCall,
        ticket_id: str | None = None,
    ) -> QFAToolResult:
        tool_metadata = dict(tool_call.metadata)
        tool_metadata["trace_id"] = self._runtime_context.trace_id
        token = set_approved_ticket_id(ticket_id)
        try:
            try:
                result = await self._capability_hub.invoke(
                    CapabilityRequest(
                        capability_id=tool_call.capability_id,
                        payload=tool_call.payload,
                        metadata=tool_metadata,
                        ticket_id=ticket_id,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                raise QFAInvalidConfigError(
                    format_user_facing_error(exc, summary=f"调用工具 {tool_call.capability_id} 失败")
                ) from exc
        finally:
            reset_approved_ticket_id(token)
        capability = self._capability_hub.get_capability(tool_call.capability_id)
        if capability is None:
            raise QFAInvalidConfigError(f"找不到工具能力描述: {tool_call.capability_id}")
        return self._to_tool_result(tool_call=tool_call, capability=capability, result=result)

    async def send_message(self, channel: QFAEnum.Channel, text: str) -> None:
        if channel != QFAEnum.Channel.Feishu:
            raise QFAInvalidConfigError(f"当前仅支持飞书消息发送，收到: {channel}")
        if self._channel_gateway is None:
            raise QFAInvalidConfigError("当前上下文未注入 Channel Gateway，无法发送消息")
        await self._channel_gateway.feishu_sender.send_text_reply(
            ReplyText(content=text),
            self._event,
        )

    async def send_feishu_card_message(
        self,
        template_id: str,
        template_variable: dict[str, Any],
    ) -> None:
        if self._channel_gateway is None:
            raise QFAInvalidConfigError("当前上下文未注入 Channel Gateway，无法发送消息")
        
        await self._channel_gateway.feishu_sender.send_feishu_card_reply(
            FeishuReplyCard(
                template_id=template_id,
                template_variable=template_variable
            ),
            self._event
        )

    async def download_image(self, file_id: str) -> str:
        """从渠道下载图片到本地。"""
        if self._channel_gateway is None:
            raise QFAInvalidConfigError("当前上下文未注入 Channel Gateway，无法下载文件")
        # 使用当前事件的消息 ID
        return await self._channel_gateway.feishu_sender.download_image(
            message_id=self._event.message_id, 
            file_key=file_id
        )

    def record(self, event_name: str, payload: dict[str, Any] | str, level: str = "INFO") -> None:
        if self._observability is None:
            return
        self._observability.record(
            self._runtime_context.trace_id,
            {"event": event_name, "payload": payload},
            level,
        )

    def _to_model_output(self, result: CapabilityResult) -> QFAModelOutput:
        if not result.success:
            failed_response = ModelResponse(
                model_name="unknown-model",
                content=result.error_message or "",
                success=False,
                finish_reason="error",
                provider_id=None,
            )
            return QFAModelOutput(
                model_response=failed_response,
                assistant_message=None,
                tool_calls=(),
            )

        # 1. 自动推导与反序列化 (T3 架构核心)
        cap_desc = self._capability_hub.get_capability(result.capability_id)
        if not cap_desc:
            raise QFAInvalidConfigError(f"无法获取能力描述: {result.capability_id}")

        # 验证并还原为 Model 实例 (SchemaTranslator 会自动处理包裹的 'result' 字段)
        parsed_obj = SchemaTranslator.validate_payload(cap_desc.output_model, result.output)
        
        # 提取真正的返回值 (ModelResponse 实例)
        output: ModelResponse = getattr(parsed_obj, "result")
        assert isinstance(output, ModelResponse), f"期望 ModelResponse，实际得到: {type(output)}"

        # 2. 转换逻辑
        return QFAModelOutput(
            model_response=output,
            assistant_message=output.assistant_message,
            tool_calls=output.tool_calls,
        )

    def _to_tool_result(
        self,
        tool_call: ParsedToolCall,
        capability: CapabilityDescription,
        result: CapabilityResult,
    ) -> QFAToolResult:
        tool_desc = capability.description
        ticket = None
        is_ask_ticket = False
        final_output: dict[str, object]

        if not result.success:
            if result.error_code == "requires_user_approval":
                ticket = result.metadata.get("ticket_id")
                is_ask_ticket = True
            final_output = {
                "error_code": result.error_code or "tool_execution_failed",
                "error_message": result.error_message or "工具执行失败",
            }
        else:
            parsed_obj = SchemaTranslator.validate_payload(capability.output_model, result.output)
            result_value = getattr(parsed_obj, "result")
            if isinstance(result_value, dict):
                final_output = result_value
            elif hasattr(result_value, "model_dump"):
                final_output = result_value.model_dump(mode="json")
            else:
                final_output = {"result": result_value}

        return QFAToolResult(
            is_ask_ticket=is_ask_ticket,
            ticket=str(ticket) if ticket else None,
            tool_name=tool_call.capability_id,
            tool_desc=tool_desc,
            tool_args=tool_call.payload,
            output=final_output,
            tool_call=tool_call,
            tool_message=build_tool_result_message(tool_call, final_output),
        )

    def _build_messages(self, prompt: str) -> tuple[ModelMessage, ...]:
        history = self._runtime_context.memory.get("dialogue_history", [])
        if not isinstance(history, list):
            raise QFAInvalidConfigError("dialogue_history 必须为 ModelMessage 列表")
        messages: list[ModelMessage] = []
        for item in history:
            if not isinstance(item, ModelMessage):
                raise QFAInvalidConfigError("dialogue_history 中只允许存在 ModelMessage")
            messages.append(item)
        if prompt:
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
