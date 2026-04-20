import pytest

from src.domain.events import UniversalEvent, UniversalEventContent
from src.orchestration_engine.context.runtime_context import RuntimeContext
from src.domain.capabilities import CapabilityDescription, CapabilityRequest, CapabilityResult
from src.qfaos import QFAConfig, QFAEnum, QFAOS
from src.qfaos.runtime.context_facade import DefaultQFAExecutionContext, DefaultQFASessionContext
from src.skill_hub.core.capability_hub import RegisteredCapabilityHub
from src.storage_memory.bootstrap import initialize as initialize_storage_memory


def _build_event() -> UniversalEvent:
    return UniversalEvent(
        event_id="evt-1",
        timestamp=1,
        platform_type="feishu",
        user_id="user-1",
        group_id=None,
        room_id=None,
        message_id="msg-1",
        contents=(UniversalEventContent(type="text", data="hello"),),
        raw_event={"source": "test"},
        logical_uid="session-1",
    )


def _build_runtime_ctx() -> RuntimeContext:
    return RuntimeContext(
        trace_id="trace-1",
        logic_id="logic-1",
        session_id="session-1",
        memory={"dialogue_history": [{"role": "user", "content": "历史消息"}]},
        state={"ticket_asked": False},
    )


def _build_capability_hub() -> RegisteredCapabilityHub:
    hub = RegisteredCapabilityHub()

    async def model_handler(_request: CapabilityRequest) -> CapabilityResult:
        return CapabilityResult(
            capability_id="model.chat.default",
            success=True,
            output={
                "content": "",
                "tool_calls": (
                    {
                        "capability_id": "tool.calc",
                        "payload": {"a": 1, "b": 2},
                        "metadata": {},
                    },
                ),
            },
        )

    async def tool_handler(request: CapabilityRequest) -> CapabilityResult:
        if request.capability_id == "tool.need_ticket":
            return CapabilityResult(
                capability_id=request.capability_id,
                success=False,
                output={},
                error_code="requires_user_approval",
                error_message="need approval",
                metadata={"ticket_id": "ticket-1"},
            )
        return CapabilityResult(
            capability_id=request.capability_id,
            success=True,
            output={"result": "ok"},
        )

    hub.register_capability(
        CapabilityDescription(
            capability_id="model.chat.default",
            domain="model",
            name="model_minimax_chat",
            description="minimax",
        ),
        model_handler,
    )
    hub.register_capability(
        CapabilityDescription(
            capability_id="tool.calc",
            domain="tool",
            name="calc",
            description="计算工具",
        ),
        tool_handler,
    )
    hub.register_capability(
        CapabilityDescription(
            capability_id="tool.need_ticket",
            domain="tool",
            name="need_ticket",
            description="审批工具",
        ),
        tool_handler,
    )
    return hub


@pytest.mark.asyncio
async def test_session_state_and_structured_outputs():
    storage = initialize_storage_memory(redis_url=None)
    hub = _build_capability_hub()
    event = _build_event()
    runtime_ctx = _build_runtime_ctx()

    session_ctx = DefaultQFASessionContext(
        runtime_context=runtime_ctx,
        capability_hub=hub,
        storage_memory=storage,
        logic_id="logic-1",
        event=event,
        channel_gateway=None,
        observability=None,
    )
    exec_ctx = DefaultQFAExecutionContext(session_ctx=session_ctx, capability_hub=hub)

    got = exec_ctx.get_session_ctx("any-session")
    assert got is session_ctx
    got.state["ticket_asked"] = True
    assert runtime_ctx.state["ticket_asked"] is True

    model_cfg = QFAConfig.Model.MiniMax(model_name="minimax-text-01", api_key="k", base_url="u")
    model_output = await session_ctx.model_ask(model_cfg, "请计算", tools_mode="all")
    assert model_output.is_pytool_call is True
    assert model_output.tool_call is not None

    normal_tool = await session_ctx.call_pytool(
        {"capability_id": "tool.calc", "payload": {"a": 1, "b": 2}, "metadata": {}}
    )
    assert normal_tool.is_ask_ticket is False
    assert normal_tool.output == {"result": "ok"}
    assert normal_tool.tool_name == "tool.calc"

    ask_tool = await session_ctx.call_pytool(
        {"capability_id": "tool.need_ticket", "payload": {}, "metadata": {}}
    )
    assert ask_tool.is_ask_ticket is True
    assert ask_tool.ticket == "ticket-1"
    assert ask_tool.tool_name == "tool.need_ticket"


def test_custom_execute_registration():
    agent = QFAOS()

    @agent.custom_execute
    async def _execute(_event, _ctx):
        return None

    assert agent.execute_handler is _execute


def test_custom_execute_rejects_sync_function():
    agent = QFAOS()

    def _sync_execute(_event, _ctx):
        return None

    with pytest.raises(Exception):
        agent.custom_execute(_sync_execute)


def test_builtin_exports_available():
    from src.qfaos import BrowserUsePyTool, ToolSecurityPrimitive

    assert BrowserUsePyTool is not None
    assert ToolSecurityPrimitive is not None
