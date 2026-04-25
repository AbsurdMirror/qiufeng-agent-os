from typing import Any, Literal

from src.domain.events import UniversalEvent
from src.domain.responses import ReplyText, FeishuReplyCard
from src.channel_gateway.exports import ChannelGatewayExports
from src.observability_hub.exports import ObservabilityHubExports
from src.orchestration_engine.context.runtime_context import RuntimeContext
from src.domain.models import ModelMessage, ModelResponse
from src.domain.capabilities import CapabilityDescription, CapabilityRequest, CapabilityResult
from src.domain.translators.schema_translator import SchemaTranslator
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
from src.domain.memory import HotMemoryItem
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

    async def add_memory(self, content: str, role: str = "assistant") -> None:
        item = HotMemoryItem(
            trace_id=self._runtime_context.trace_id,
            role=role,
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
            dialogue.append({"role": role, "content": content})

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
            return QFAModelOutput(
                is_pytool_call=False,
                tool_call=None,
                tool_call_str=None,
                is_answer=True,
                response=result.error_message or "",
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
        # 优先检查工具调用 (T4 模型能力规范)
        if output.tool_calls:
            # 提取第一个工具调用进行处理
            first_call = output.tool_calls[0]
            # 兼容处理：CapabilityRequest 转为 QFA 内部使用的 dict 格式
            tool_call_dict = {
                "capability_id": first_call.capability_id,
                "payload": first_call.payload,
                "metadata": first_call.metadata,
            }
            return QFAModelOutput(
                is_pytool_call=True,
                tool_call=tool_call_dict,
                tool_call_str=output.tool_call_str,
                is_answer=False,
                response=None,
            )

        # 无工具调用，则视为普通文本回答
        return QFAModelOutput(
            is_pytool_call=False,
            tool_call=None,
            tool_call_str=None,
            is_answer=True,
            response=output.content or "",
        )

    def _to_tool_result(
        self,
        capability_id: str,
        tool_args: dict[str, Any],
        result: CapabilityResult,
    ) -> QFAToolResult:
        # 1. 获取能力描述 (T3 架构核心)
        capability = self._capability_hub.get_capability(capability_id)
        tool_desc = capability.description if capability else f"工具 {capability_id}"

        # 2. 处理失败场景
        if not result.success:
            if result.error_code == "requires_user_approval":
                ticket = result.metadata.get("ticket_id")
                return QFAToolResult(
                    is_ask_ticket=True,
                    ticket=str(ticket) if ticket else None,
                    tool_name=capability_id,
                    tool_desc=tool_desc,
                    tool_args=tool_args,
                    output=dict(result.output),  # 审批阶段的 output 通常包含提示信息
                )
            else:
                return QFAToolResult(
                    is_ask_ticket=False,
                    ticket=None,
                    tool_name=capability_id,
                    tool_desc=tool_desc,
                    tool_args=tool_args,
                    output={
                        "error_code": result.error_code,
                        "error_message": result.error_message,
                    },
                )

        # 3. 处理成功场景：自动推导与反序列化 (T3 架构核心)
        if not capability:
            # 兜底：如果没有能力描述，回退到原始字典
            return QFAToolResult(
                is_ask_ticket=False,
                ticket=None,
                tool_name=capability_id,
                tool_desc=tool_desc,
                tool_args=tool_args,
                output=dict(result.output),
            )

        # 验证并还原为 Model 实例
        parsed_obj = SchemaTranslator.validate_payload(capability.output_model, result.output)
        
        # 提取真正的返回值 (由 SchemaTranslator 包装在 result 字段中)
        raw_output = getattr(parsed_obj, "result")
        
        # 统一转为 dict 返回给编排层 (QFA 契约要求 output 为 dict)
        if hasattr(raw_output, "model_dump"):
            final_output = raw_output.model_dump(mode="json")
        elif hasattr(raw_output, "__dict__"):
            final_output = dict(raw_output)
        else:
            final_output = {"result": raw_output}

        return QFAToolResult(
            is_ask_ticket=False,
            ticket=None,
            tool_name=capability_id,
            tool_desc=tool_desc,
            tool_args=tool_args,
            output=final_output,
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
