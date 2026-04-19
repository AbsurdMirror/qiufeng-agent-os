from asyncio import to_thread
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from src.model_provider.contracts import (
    ModelMessage,
    ModelProviderClient,
    ModelResponseParseConfig,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)
from src.orchestration_engine.contracts import (
    CapabilityDescription,
    CapabilityRequest,
    CapabilityResult,
)
from src.skill_hub.contracts import PyTool
from src.skill_hub.primitives.security import with_security_policy, default_security_policy

# ============================================================
# 能力中心 —— 注册中心与调度总线 (Capability Hub)
#
# 本模块是整个 Agent-OS 的"总机"。所有供大模型使用的工具、甚至模型自身发起的
# 对话请求，都被抽象为统一的「能力 (Capability)」，并注册到 RegisteredCapabilityHub。
#
# T5 架构升级 (SH-P0-01)：
#   在 `register_capability` 时，统一注入了安全管控拦截器 `with_security_policy`。
#   这保证了所有的调用（无论是内置工具还是外部扩展）都会强制经过安全原语的审计。
# ============================================================


CapabilityHandler = Callable[[CapabilityRequest], Awaitable[CapabilityResult]]


class RegisteredCapabilityHub:
    """
    编排层可见的统一能力注册中心。
    
    设计意图：
    实现 `CapabilityHub` 协议，提供能力的注册、发现和调用。
    所有的工具（PyTool）和模型路由都会注册到这里，编排层只需要通过唯一的 `invoke` 方法
    和能力 ID，就能调用底层的任何功能。这也为拦截器（审计、日志、安全验证）提供了单一挂载点。
    """
    def __init__(self) -> None:
        self._capabilities: dict[str, CapabilityDescription] = {}
        self._handlers: dict[str, CapabilityHandler] = {}

    def register_capability(
        self,
        capability: CapabilityDescription,
        handler: CapabilityHandler,
    ) -> CapabilityDescription:
        """
        注册一个能力及其对应的异步处理函数。
        
        T5 新增：针对工具类型的能力，自动使用 default_security_policy 包装，
        拦截越权或非法的资源访问。模型能力不应用该沙盒以避免网络误伤。
        """
        self._capabilities[capability.capability_id] = capability
        # 仅针对 tool 域（即 PyTools）应用安全原语拦截，不对 model 等路由施加沙盒
        # [业务设计补充]：
        # 如果一刀切地把大模型的纯对话网络请求（domain="model"）也框进这个底层安全沙盒，
        # 因为沙盒默认拦截未知路径，会导致大模型彻底变成“聋子和哑巴”（甚至无法请求 OpenAI/MiniMax 接口）。
        # 因此必须进行域隔离，特权网络请求放行，只约束落地执行阶段的危险动作。
        if capability.domain == "tool":
            safe_handler = with_security_policy(default_security_policy)(handler)
        else:
            safe_handler = handler
        self._handlers[capability.capability_id] = safe_handler
        return capability

    def list_capabilities(self) -> tuple[CapabilityDescription, ...]:
        return tuple(self._capabilities.values())

    def get_capability(self, capability_id: str) -> CapabilityDescription | None:
        return self._capabilities.get(capability_id)

    async def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        """
        统一的调用入口。
        所有编排层的能力调用都将通过此方法分发。
        """
        capability = self.get_capability(request.capability_id)
        if capability is None:
            return CapabilityResult(
                capability_id=request.capability_id,
                success=False,
                output={},
                error_code="capability_not_found",
                error_message=f"capability '{request.capability_id}' is not registered",
            )
        handler = self._handlers[request.capability_id]
        
        # 异常隔离兜底：如果 handler 内部由于（如模型超时、JSON 解析失败等）抛出未捕获异常，
        # 在此处被捕获并转化为 CapabilityResult(success=False)，防止整个编排主协程崩溃。
        try:
            result = await handler(request)
        except Exception as e:
            return CapabilityResult(
                capability_id=request.capability_id,
                success=False,
                output={},
                error_code="capability_execution_failed",
                error_message=str(e),
                metadata={"domain": capability.domain}
            )
        
        metadata = dict(result.metadata)
        metadata.setdefault("domain", capability.domain)
        return CapabilityResult(
            capability_id=result.capability_id,
            success=result.success,
            output=dict(result.output),
            error_code=result.error_code,
            error_message=result.error_message,
            metadata=metadata,
        )


class ModelCapabilityRouter:
    """
    模型能力路由，将底层的 `ModelProviderClient` 包装为标准的 `Capability`。
    
    设计意图：
    将模型推理能力也视作一种普通的工具能力注册到 Hub 中，
    实现 "一切皆能力" 的统一调用模型。
    
    缺点：
    它在注册时使用了反向注入（传入 hub 并调用 `register_into`）。
    这种耦合设计在扩展更多工具或能力域时，会导致注册代码变得冗长。
    """
    def __init__(self, model_client: ModelProviderClient) -> None:
        self._model_client = model_client
        self._capability = CapabilityDescription(
            capability_id="model.chat.default",
            domain="model",
            name="model_chat_default",
            description="通过统一模型提供方发起标准对话推理请求。",
            input_schema={
                "type": "object",
                "properties": {
                    "messages": {
                        "type": "python_tuple",
                        "python_type": "tuple[ModelMessage, ...]",
                        "items": {
                            "type": "object",
                            "python_type": "ModelMessage",
                            "properties": {
                                "role": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["role", "content"],
                        },
                    },
                    "model_name": {"type": "string"},
                    "model_tag": {"type": "string"},
                    "temperature": {"type": "number"},
                    "top_p": {"type": "number"},
                    "max_tokens": {"type": "integer"},
                    "tools": {
                        "type": "python_tuple",
                        "python_type": "tuple[CapabilityDescription, ...]",
                        "items": {"type": "object", "python_type": "CapabilityDescription"},
                    },
                    "output_schema": {"type": "object"},
                    "schema_max_retries": {"type": "integer"},
                    "metadata": {"type": "object"},
                },
                "additionalProperties": True,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "model_name": {"type": "string"},
                    "content": {"type": "string"},
                    "finish_reason": {"type": "string"},
                    "provider_id": {"type": "string"},
                    "usage": {"type": "object"},
                    "parsed": {"type": "object"},
                    "tool_calls": {"type": "array"},
                    "raw": {"type": "object"},
                },
                "additionalProperties": True,
            },
            metadata={"provider": "router", "kind": "model"},
        )

    def capabilities(self) -> tuple[CapabilityDescription, ...]:
        return (self._capability,)

    def register_into(self, hub: RegisteredCapabilityHub) -> None:
        hub.register_capability(
            self._capability,
            self._invoke_model,
        )

    async def _invoke_model(
        self,
        request: CapabilityRequest,
    ) -> CapabilityResult:
        model_request, error = _build_model_request(request=request)
        if error is not None:
            return error
        response = await to_thread(self._model_client.completion, model_request)
        return _build_model_result(
            request=request,
            response=response
        )


def register_pytools(
    hub: RegisteredCapabilityHub,
    pytools: Iterable[PyTool],
) -> None:
    for pytool in pytools:
        hub.register_capability(pytool.capability, pytool.invoke)


def _build_model_request(
    *,
    request: CapabilityRequest,
) -> tuple[ModelRequest, CapabilityResult | None]:
    payload = dict(request.payload)
    messages, message_error = _normalize_messages(payload)
    if message_error is not None:
        return ModelRequest(messages=()), CapabilityResult(
            capability_id=request.capability_id,
            success=False,
            output={},
            error_code="invalid_model_request",
            error_message=message_error,
            metadata={"domain": "model"},
        )
    tools, tools_error = _normalize_tools(payload)
    if tools_error is not None:
        return ModelRequest(messages=messages), CapabilityResult(
            capability_id=request.capability_id,
            success=False,
            output={},
            error_code="invalid_model_request",
            error_message=tools_error,
            metadata={"domain": "model"},
        )
    payload_metadata = payload.get("metadata", {})
    metadata = dict(request.metadata)
    if isinstance(payload_metadata, dict):
        metadata.update(payload_metadata)
    model_request = ModelRequest(
        messages=messages,
        model_name=_normalize_optional_string(payload.get("model_name")),
        model_tag=_normalize_optional_string(payload.get("model_tag")),
        temperature=_normalize_optional_float(payload.get("temperature")),
        top_p=_normalize_optional_float(payload.get("top_p")),
        max_tokens=_normalize_optional_int(payload.get("max_tokens")),
        tools=tools,
        response_parse=ModelResponseParseConfig(
            output_schema = payload.get("output_schema"),
            schema_max_retries = _normalize_optional_int(payload.get("schema_max_retries"))
        ),
        metadata=metadata,
    )
    return model_request, None


def _normalize_messages(payload: dict[str, Any]) -> tuple[tuple[ModelMessage, ...], str | None]:
    raw_messages = payload.get("messages")
    if not raw_messages:
        return (), "model_messages_required"
    if not isinstance(raw_messages, tuple):
        return (), "model_messages_must_be_tuple"
    for item in raw_messages:
        if not isinstance(item, ModelMessage):
            return (), "model_messages_items_must_be_model_message"
    return raw_messages, None


def _normalize_tools(payload: dict[str, Any]) -> tuple[tuple[CapabilityDescription, ...], str | None]:
    raw_tools = payload.get("tools")
    if raw_tools is None:
        return (), None
    if not isinstance(raw_tools, tuple):
        return (), "model_tools_must_be_tuple"
    for item in raw_tools:
        if not isinstance(item, CapabilityDescription):
            return (), "model_tools_items_must_be_capability_description"
    return raw_tools, None


def _normalize_optional_string(value: Any) -> str | None:
    """
    规范化可选字符串字段：
    - 仅接受 str；空白字符串视为 None；
    - 其他类型一律返回 None（不做兼容转换）。
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_optional_float(value: Any) -> float | None:
    """
    规范化可选浮点字段：
    - 仅接受 int/float（排除 bool）；
    - 其他类型一律返回 None（不做兼容转换）。
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _normalize_optional_int(value: Any) -> int | None:
    """
    规范化可选整数字段：
    - 仅接受 int（排除 bool）；
    - 其他类型一律返回 None（不做兼容转换）。
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _build_model_result(
    *,
    request: CapabilityRequest,
    response: ModelResponse,
) -> CapabilityResult:
    """
    将模型层返回的 ModelResponse 映射为编排层可消费的 CapabilityResult。

    职责边界说明：
    1. 这里只做字段映射与错误翻译，不做解析、校验和重试策略；
    2. success/error 语义以 ModelResponse 为准，避免在 Skill Hub 再次推断状态；
    3. 将 parsed/tool_calls/raw 全量透传，便于编排层决策下一步动作。
    """
    raw = dict(response.raw)
    success = response.success
    error_code = None
    error_message = None
    if not success:
        error_code = str(raw.get("reason") or "model_request_failed")
        error_message = str(raw.get("message") or raw.get("reason") or "model_request_failed")
    return CapabilityResult(
        capability_id=request.capability_id,
        success=success,
        output={
            "model_name": response.model_name,
            "content": response.content,
            "finish_reason": response.finish_reason,
            "provider_id": response.provider_id,
            "usage": response.usage.to_dict() if response.usage else {},
            "parsed": response.parsed,
            "tool_calls": tuple(
                {
                    "capability_id": call.capability_id,
                    "payload": dict(call.payload),
                    "metadata": dict(call.metadata),
                }
                for call in response.tool_calls
            ),
            "raw": raw,
        },
        error_code=error_code,
        error_message=error_message,
        metadata={
            "domain": "model",
        },
    )
