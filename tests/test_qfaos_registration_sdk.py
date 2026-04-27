import asyncio
import pytest
from typing import Annotated
from pydantic import Field

from src.qfaos import QFAOS, QFAConfig, QFAEnum, qfaos_pytool, QFAEvent
from src.domain.capabilities import CapabilityDescription, CapabilityRequest, CapabilityResult
from src.domain.models import ModelMessage, ToolCallFunction, ToolInvocation
from src.domain.translators.model_interactions import ParsedToolCall

# 1. 声明式工具类 (用于方式 2)
class MathService:
    @qfaos_pytool(id="tool.instance.sub")
    def subtract(
        self, 
        a: Annotated[int, Field(description="被减数")], 
        b: Annotated[int, Field(description="减数")]
    ) -> Annotated[int, Field(description="差")]:
        """执行减法运算。"""
        return a - b

@pytest.mark.asyncio
async def test_qfaos_triple_registration_and_execution():
    """
    一个测试项覆盖三种工具注册方式，并通过 custom_execute 验证调用。
    """
    agent = QFAOS()
    
    # --- 注册方式 1: 使用 @agent.pytool 装饰器 ---
    @agent.pytool("func_add")
    def add_numbers(
        a: Annotated[int, Field(description="第一个加数")],
        b: Annotated[int, Field(description="第二个加数")]
    ) -> Annotated[int, Field(description="和")]:
        """执行加法运算。"""
        return a + b

    # --- 注册方式 2: 使用 register_pytool_instance 注册类实例 ---
    math_service = MathService()
    agent.register_pytool_instance(math_service)

    # --- 注册方式 3: 使用 @qfaos_pytool + register_pytool 手动两步注册 ---
    @qfaos_pytool(id="manual_mul")
    def manual_multiply(
        a: Annotated[int, Field(description="因数 A")], 
        b: Annotated[int, Field(description="因数 B")]
    ) -> Annotated[int, Field(description="积")]:
        """执行乘法运算。"""
        return a * b

    agent.register_pytool(manual_multiply)

    # 验证点记录器
    results = {}

    # --- 编排执行逻辑 ---
    @agent.custom_execute
    async def handle_event(event: QFAEvent, ctx):
        session_id = event.session_id
        session_ctx = ctx.get_session_ctx(session_id)

        def _build_tool_call(capability_id: str, payload: dict[str, object]) -> ParsedToolCall:
            return ParsedToolCall(
                invocation=ToolInvocation(
                    id=None,
                    function=ToolCallFunction(
                        name=capability_id,
                        arguments='{"payload":"omitted"}',
                    ),
                ),
                request=CapabilityRequest(
                    capability_id=capability_id,
                    payload=payload,
                    metadata={},
                ),
            )
        
        # 尝试调用工具 1 (装饰器方式)
        res1 = await session_ctx.call_pytool(_build_tool_call("tool.func_add", {"a": 10, "b": 20}))
        results["add"] = res1.output.get("result")
        
        # 尝试调用工具 2 (实例方式)
        res2 = await session_ctx.call_pytool(_build_tool_call("tool.instance.sub", {"a": 50, "b": 15}))
        results["sub"] = res2.output.get("result")
        
        # 尝试调用工具 3 (手动方式)
        res3 = await session_ctx.call_pytool(_build_tool_call("tool.manual_mul", {"a": 6, "b": 7}))
        results["mul"] = res3.output.get("result")

    # --- 模拟运行环境并触发调用 ---
    # 由于 agent.run() 是阻塞的且涉及多进程，我们直接通过内部初始化逻辑进行模拟
    # 1. 注册必要的配置以通过校验
    agent.register_channel(QFAEnum.Channel.Feishu, QFAConfig.Channel.Feishu(app_id="x", app_secret="x", mode=QFAEnum.Feishu.Mode.long_connection))
    agent.register_model(QFAEnum.Model.MiniMax, QFAConfig.Model.MiniMax(model_name="m", api_key="k"))
    agent.register_memory(QFAConfig.Memory(backend=QFAEnum.Memory.Backend.in_memory))
    agent.register_observability_log(QFAConfig.Observability.Log())
    
    # 2. 模拟 run 内部的初始化逻辑来构建 hub
    # 这里我们手动触发注册流程
    from src.skill_hub.bootstrap import initialize as initialize_skill_hub
    from src.skill_hub.core.capability_hub import register_pytools
    
    skill_hub = initialize_skill_hub()
    hub = skill_hub.capability_hub
    
    # 2. 模拟 run 内部的注册顺序
    # (1) 注册方式 1 & 3 的工具 (它们都在 tool_registry 中)
    user_tools = tuple(
        agent.tools.get(tool_id)
        for tool_id in agent.tools.list_tools()
        if agent.tools.get(tool_id) is not None
    )
    register_pytools(hub, user_tools)
    
    # (2) 注册方式 2 的实例
    if hasattr(agent.tools, "_instances"):
        for instance in agent.tools._instances:
            hub.register_instance_capabilities(instance)
            
    # 3. 构造 mock 上下文进行调用
    from src.orchestration_engine.context.runtime_context import RuntimeContext
    from src.qfaos.runtime.context_facade import DefaultQFAExecutionContext, DefaultQFASessionContext
    from src.domain.events import UniversalEvent, UniversalEventContent
    from unittest.mock import MagicMock
    
    mock_runtime_ctx = RuntimeContext(trace_id="t1", logic_id="test_logic", session_id="s1")
    mock_universal_event = UniversalEvent(
        event_id="e1",
        timestamp=123456789,
        platform_type="feishu",
        user_id="u1",
        group_id=None,
        room_id=None,
        message_id="m1",
        contents=(UniversalEventContent(type="text", data="test"),),
        raw_event={},
        logical_uid="s1"
    )
    
    session_ctx = DefaultQFASessionContext(
        runtime_context=mock_runtime_ctx,
        capability_hub=hub,
        storage_memory=MagicMock(),
        logic_id="test_logic",
        event=mock_universal_event,
        channel_gateway=None,
        observability=None
    )
    
    exec_ctx = DefaultQFAExecutionContext(
        session_ctx=session_ctx,
        capability_hub=hub
    )
    
    mock_event = QFAEvent(
        channel=QFAEnum.Channel.Feishu,
        type=QFAEnum.Event.TextMessage,
        session_id="s1",
        payload="hi"
    )
    
    # 4. 执行
    await agent.execute_handler(mock_event, exec_ctx)
    
    # --- 最终断言 ---
    assert results["add"] == 30
    assert results["sub"] == 35
    assert results["mul"] == 42
    print("\n[SUCCESS] 所有三种注册方式的工具均已成功调用！")
    print(f"结果汇总: {results}")

@pytest.mark.asyncio
async def test_qfaos_registration_invalid_format():
    """
    验证 3 种注册方式在输入/输出不规范时的 6 种报错情况。
    """
    agent = QFAOS()

    # --- 1. @agent.pytool 方式 (2 种情况) ---
    print("\n[TEST 1/6] @agent.pytool + 输入不规范")
    with pytest.raises(TypeError) as excinfo:
        @agent.pytool("t1")
        def f1(a: int) -> Annotated[int, Field(description="o")]: pass
    err_msg = str(excinfo.value)
    assert "must use Annotated[...] for parameter schema parsing" in err_msg
    assert "test_qfaos_registration_sdk.py" in err_msg
    assert "f1" in err_msg
    print(f"捕获到预期错误: {err_msg}")

    print("[TEST 2/6] @agent.pytool + 输出不规范")
    with pytest.raises(TypeError) as excinfo:
        @agent.pytool("t2")
        def f2(a: Annotated[int, Field(description="i")]) -> int: pass
    err_msg = str(excinfo.value)
    assert "must use Annotated[...] for return schema parsing" in err_msg
    assert "test_qfaos_registration_sdk.py" in err_msg
    assert "f2" in err_msg
    print(f"捕获到预期错误: {err_msg}")

    # --- 2. register_pytool_instance 方式 (2 种情况) ---
    print("[TEST 3/6] register_pytool_instance + 输入不规范")
    with pytest.raises(TypeError) as excinfo:
        class S1:
            @qfaos_pytool(id="c1")
            def m1(self, x: int) -> Annotated[int, Field(description="o")]: pass
    err_msg = str(excinfo.value)
    assert "must use Annotated[...] for parameter schema parsing" in err_msg
    assert "S1.m1" in err_msg
    print(f"捕获到预期错误: {err_msg}")

    print("[TEST 4/6] register_pytool_instance + 输出不规范")
    with pytest.raises(TypeError) as excinfo:
        class S2:
            @qfaos_pytool(id="c2")
            def m2(self, x: Annotated[int, Field(description="i")]) -> int: pass
    err_msg = str(excinfo.value)
    assert "must use Annotated[...] for return schema parsing" in err_msg
    assert "S2.m2" in err_msg
    print(f"捕获到预期错误: {err_msg}")

    # --- 3. @qfaos_pytool + register_pytool 方式 (2 种情况) ---
    print("[TEST 5/6] register_pytool + 输入不规范")
    with pytest.raises(TypeError) as excinfo:
        @qfaos_pytool(id="t5")
        def f5(a: int) -> Annotated[int, Field(description="o")]: return a
        agent.register_pytool(f5)
    err_msg = str(excinfo.value)
    assert "must use Annotated[...] for parameter schema parsing" in err_msg
    assert "f5" in err_msg
    print(f"捕获到预期错误: {err_msg}")

    print("[TEST 6/6] register_pytool + 输出不规范")
    with pytest.raises(TypeError) as excinfo:
        @qfaos_pytool(id="t6")
        def f6(a: Annotated[int, Field(description="i")]) -> int: return a
        agent.register_pytool(f6)
    err_msg = str(excinfo.value)
    assert "must use Annotated[...] for return schema parsing" in err_msg
    assert "f6" in err_msg
    print(f"捕获到预期错误: {err_msg}")

    print("\n[SUCCESS] 3x2=6 种不规范注册场景已全部覆盖并成功捕获报错！")

if __name__ == "__main__":
    # 运行原有的集成测试
    asyncio.run(test_qfaos_triple_registration_and_execution())
    # 运行新增的异常测试
    asyncio.run(test_qfaos_registration_invalid_format())
