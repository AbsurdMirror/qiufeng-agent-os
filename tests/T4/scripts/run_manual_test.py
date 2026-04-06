"""
Agent-OS T4 阶段手动联调测试脚本
=============================================
此脚本会组装一个"完整的 Simple Agent"并挂载到飞书长连接：
  - 接通 MiniMax 模型
  - 注册测试用的 Dummy Tools（get_weather / calculate_sum）
  - 实现含工具调用的完整 Agent 执行闭环（ReAct 风格）
  - 从 Redis 中加载历史记忆（上下文注入）
  - 执行完后将对话写回 Redis 并持久化状态

运行方式（在项目根目录）：
    PYTHONPATH=. python -m tests.T4.scripts.run_manual_test

如果 MiniMax 的 Key 已配置好（QF_MINIMAX_API_KEY 或 MINIMAX_API_KEY），
直接打开飞书开始按剧本对话即可。

停止方式：直接 Ctrl+C 即可（该操作同时模拟"进程死亡"，用于测试重启后记忆能否找回）。
"""

import asyncio
import json
import uuid
from typing import Annotated, Any
from pydantic import Field

from src.app.bootstrap import Application, build_application
from src.app.config import load_config
from src.channel_gateway.events import UniversalEvent
from src.model_provider.contracts import ModelMessage, ModelRequest
from src.orchestration_engine.contracts import CapabilityDescription, CapabilityRequest, CapabilityResult
from src.orchestration_engine.context_manager import StateContextManager
from src.skill_hub.capability_hub import RegisteredCapabilityHub
from src.skill_hub.tool_parser import parse_doxygen_to_json_schema
from src.storage_memory.contracts import HotMemoryItem
from src.storage_memory.redis_store import HAS_REDIS


# ===========================================================
# Step 1: 定义测试 Dummy Tools（含 Annotated/Field 标注）
# ===========================================================

def get_weather(
    city: Annotated[str, Field(description="城市名称，例如北京、上海")]
) -> str:
    """获取指定城市当前的天气情况"""
    print(f"  [🔧 Tool] get_weather(city='{city}') -> 天气晴朗，25度")
    return f"{city}天气晴朗，25度"


def calculate_sum(
    a: Annotated[int, Field(description="第一个加数")],
    b: Annotated[int, Field(description="第二个加数")]
) -> str:
    """计算两个整数相加的结果"""
    print(f"  [🔧 Tool] calculate_sum(a={a}, b={b}) -> {a + b}")
    return f"{a} 加上 {b} 的结果是 {a + b}"


# ===========================================================
# Step 2: 将函数包装为 CapabilityDescription + 异步 handler
# ===========================================================

def _wrap_func_as_capability(func) -> tuple[CapabilityDescription, Any]:
    """利用 T4 的 ToolParser 将 Python 函数包装为标准 Capability"""
    schema = parse_doxygen_to_json_schema(func)
    desc = CapabilityDescription(
        capability_id=f"tool.test.{func.__name__}",
        domain="tool.test",
        name=func.__name__,
        description=func.__doc__ or "无描述",
        input_schema=schema,
        output_schema={"type": "object", "properties": {"result": {"type": "string"}}},
        metadata={"kind": "dummy_tool"},
    )

    async def handler(request: CapabilityRequest) -> CapabilityResult:
        try:
            result = func(**request.payload)
            return CapabilityResult(
                capability_id=desc.capability_id,
                success=True,
                output={"result": str(result)},
                metadata={},
            )
        except Exception as e:
            return CapabilityResult(
                capability_id=desc.capability_id,
                success=False,
                output={},
                error_code="tool_execution_failed",
                error_message=str(e),
                metadata={},
            )

    return desc, handler


# ===========================================================
# Step 3: 核心 Agent 执行函数（完整的 ReAct 执行闭环）
# ===========================================================

async def _execute_agent(
    event: UniversalEvent,
    app: Application,
    capability_hub: RegisteredCapabilityHub,
    tool_descs: list[CapabilityDescription],
) -> str:
    """
    完整的 Simple Agent 执行逻辑：
    1. 从 Redis 拉取历史热记忆（OE-P0-04）
    2. 将历史 + 工具描述 + 当前消息组装成 MiniMax 请求
    3. 调用 MiniMax 模型
    4. 如果模型请求 Tool Call -> 执行工具 -> 把结果反送给模型
    5. 得到最终文本回复
    6. 将本轮对话写回 Redis（SM-P0-02 热记忆）并持久化 state（OE-P0-06）
    """
    storage = app.modules.storage_memory
    model_client = app.modules.model_provider.client
    trace_id = app.modules.observability_hub.trace_id_generator()

    logic_id = "simple_agent_test"
    # 注意：event.logical_uid 是 SessionContextController 在内存中生成的 UUID，
    # 每次进程重启后同一个 open_id 会生成不同的 UUID，导致 Redis 中的历史找不到。
    # T4 测试阶段直接用稳定的物理 ID (open_id) 作为 session_id，保证跨重启可续接。
    # 真正解决需 T4+ 将 UUID 映射关系也持久化到 Redis。
    session_id = event.user_id  # 使用稳定的 open_id（飞书唯一用户ID）

    print(f"\n[📥 Event] trace_id={trace_id} | session_id={session_id[:16]}...")
    print(f"  用户说: {event.text}")

    # --- OE-P0-04: 从 Redis 拉取历史记忆 ---
    history_items = await storage.read_hot_memory(logic_id, session_id, limit=10)
    history_messages: list[dict] = [
        {"role": item.role, "content": item.content}
        for item in history_items
    ]
    print(f"  [📚 Memory] 读取到 {len(history_messages)} 条历史记忆")

    # --- 构建 Tool Schema（Function Calling 格式）---
    tools_payload = [
        {
            "type": "function",
            "function": {
                "name": d.name,
                "description": d.description,
                "parameters": d.input_schema,
            },
        }
        for d in tool_descs
    ]

    # --- 构建完整消息列表 ---
    system_prompt = (
        "你是一个智能助手。你具备以下工具，在需要时请通过 function call 的方式调用它们。\n"
        "当用户提问时，优先根据历史上下文回答，如果需要实时数据则调用工具。"
    )
    messages_for_model = [{"role": "system", "content": system_prompt}]
    messages_for_model.extend(history_messages)
    messages_for_model.append({"role": "user", "content": event.text})

    # --- 调用 MiniMax 模型（使用 asyncio.to_thread 避免阻塞事件循环）---
    print(f"  [🤖 Model] 正在调用 MiniMax，共 {len(messages_for_model)} 条消息...")

    model_request = ModelRequest(
        messages=tuple(ModelMessage(role=m["role"], content=m["content"]) for m in messages_for_model),
        model_tag="minimax",  # 匹配 ModelRouter.clients 字典中的 key
        metadata={"provider": "minimax", "litellm_kwargs": {"tools": tools_payload} if tools_payload else {}},
    )

    model_response = await asyncio.to_thread(model_client.invoke, model_request)
    print(f"  [🤖 Model] 模型响应: {model_response}")

    # --- 检查是否需要 Tool Call ---
    raw = model_response.raw
    tool_calls = _extract_tool_calls(raw)
    final_reply = model_response.content

    if tool_calls:
        print(f"  [⚙️  ToolCall] 模型请求调用 {len(tool_calls)} 个工具")
        tool_results_messages = []

        for call in tool_calls:
            fn_name = call.get("function", {}).get("name", "")
            fn_args_raw = call.get("function", {}).get("arguments", "{}")
            call_id = call.get("id", str(uuid.uuid4()))

            try:
                fn_kwargs = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
            except json.JSONDecodeError:
                fn_kwargs = {}

            cap_id = f"tool.test.{fn_name}"
            tool_result = await capability_hub.invoke(
                CapabilityRequest(capability_id=cap_id, payload=fn_kwargs)
            )
            result_text = tool_result.output.get("result", tool_result.error_message or "无结果")
            print(f"    -> 工具 '{fn_name}' 返回: {result_text}")

            tool_results_messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "name": fn_name,
                "content": result_text,
            })

        # 把工具结果发回模型，获取最终回复
        # ⚠️ 重要：MiniMax 要求 tool 消息必须包含 tool_call_id，assistant 消息必须包含 tool_calls。
        # 由于 ModelMessage 只有 role/content 两个字段，直接转换会丢失这两个关键字段。
        # 解决方案：通过 litellm_kwargs["messages"] 直接覆盖 build_litellm_completion_payload 中
        # 生成的 messages，从而保留完整的 dict 结构（包含 tool_call_id / tool_calls）。
        full_second_messages = (
            messages_for_model
            + [{"role": "assistant", "content": model_response.content or "", "tool_calls": tool_calls}]
            + tool_results_messages
        )
        second_request = ModelRequest(
            messages=(),  # 占位，会被 litellm_kwargs 中的 messages 覆盖
            model_tag="minimax",
            metadata={
                "provider": "minimax",
                "litellm_kwargs": {"messages": full_second_messages},  # 完整保留 tool_call_id / tool_calls
            },
        )
        print(f"  [🤖 Model] 将工具结果发回模型，获取最终回复...")
        second_response = await asyncio.to_thread(model_client.invoke, second_request)
        print(f"  [🤖 Model] 模型响应: {second_response}")
        final_reply = second_response.content

    if not final_reply:
        final_reply = "（模型未返回内容，请检查 API Key 或网络连接）"

    print(f"  [💬 Reply] {final_reply[:100]}{'...' if len(final_reply) > 100 else ''}")

    # --- SM-P0-02: 将本轮用户消息和助手回复写入热记忆 ---
    await storage.append_hot_memory(logic_id, session_id, HotMemoryItem(
        trace_id=trace_id, role="user", content=event.text
    ), max_rounds=10)
    await storage.append_hot_memory(logic_id, session_id, HotMemoryItem(
        trace_id=trace_id, role="assistant", content=final_reply
    ), max_rounds=10)
    print(f"  [💾 Memory] 本轮对话已写入 Redis 热记忆")

    # --- OE-P0-06: 持久化运行时状态 ---
    await storage.persist_runtime_state(logic_id, session_id, {
        "last_trace_id": trace_id,
        "last_user_message": event.text,
        "last_reply": final_reply,
        "turn_count": len(history_messages) // 2 + 1,
    })
    print(f"  [💾 State] 运行时状态已持久化")

    return final_reply


def _extract_tool_calls(raw: dict) -> list[dict]:
    """从模型原始响应的 raw 中提取 tool_calls 列表"""
    choices = raw.get("choices", [])
    if not choices:
        return []
    first = choices[0]
    if isinstance(first, dict):
        message = first.get("message", {})
    else:
        message = getattr(first, "message", None) or {}
        if hasattr(message, "__dict__"):
            message = vars(message)
    tool_calls = message.get("tool_calls") if isinstance(message, dict) else getattr(message, "tool_calls", None)
    if not tool_calls:
        return []
    result = []
    for tc in tool_calls:
        if isinstance(tc, dict):
            result.append(tc)
        elif hasattr(tc, "__dict__"):
            # OpenAI-style object: tc.function.name / tc.function.arguments
            fn = getattr(tc, "function", None)
            result.append({
                "id": getattr(tc, "id", str(uuid.uuid4())),
                "type": "function",
                "function": {
                    "name": getattr(fn, "name", ""),
                    "arguments": getattr(fn, "arguments", "{}"),
                },
            })
    return result


# ===========================================================
# Step 4: 发送飞书消息的回调（直接通过日志输出到终端）
# ===========================================================

async def _reply_to_feishu(event: UniversalEvent, reply: str) -> None:
    """
    当前阶段（T4）仅输出到终端，飞书回复将在 T5 阶段的响应渲染器完成后实现。
    打印格式方便在控制台直接验证 Agent 的回复内容。
    """
    print(f"\n{'='*50}")
    print(f"[飞书回复] -> {reply}")
    print(f"{'='*50}\n")


# ===========================================================
# Step 5: 主程序入口
# ===========================================================

def main():
    print("=" * 55)
    print("  Agent-OS T4 Manual Test - Simple Agent (飞书联调)")
    print("=" * 55)

    if not HAS_REDIS:
        print("[⚠️  警告] 未检测到 Redis 依赖，热记忆降级为内存存储。")
        print("         进程重启后记忆将丢失，无法测试「回合4: 断点续联」。\n")
    else:
        print("[✅ Redis] 检测到 Redis，上下文持久化已就绪。\n")

    print("[...] 正在初始化 Agent-OS 应用上下文...")
    try:
        config = load_config()
        app = build_application(config)
    except Exception as e:
        print(f"[❌ 启动失败] {e}")
        print("请先运行: PYTHONPATH=. python -m src.app.main config-feishu --app-id <id> --app-secret <secret>")
        return

    # 检查 MiniMax 配置
    from src.model_provider.minimax import probe_minimax_runtime
    mm_state = probe_minimax_runtime()
    if not mm_state.available:
        print(f"[⚠️  MiniMax] 模型未就绪: {mm_state.reason}")
        print("         请设置环境变量 QF_MINIMAX_API_KEY 和 QF_MINIMAX_MODEL。\n")
    else:
        print(f"[✅ MiniMax] 模型就绪: {mm_state.configured_model}\n")

    # 注册测试 Dummy Tools
    hub: RegisteredCapabilityHub = app.modules.skill_hub.capability_hub
    tool_descs = []
    for func in [get_weather, calculate_sum]:
        desc, handler = _wrap_func_as_capability(func)
        hub.register_capability(desc, handler)
        tool_descs.append(desc)
        print(f"[🔧 Tool] 已挂载测试工具: {desc.name}  ({desc.description})")

    print(f"\n共 {len(tool_descs)} 个测试工具就绪。")
    print("\n" + "=" * 55)
    print("  服务组装完毕！请切至飞书开始 T4 剧本测试：")
    print("  回合1: 告诉它你的代号")
    print("  回合2: 让它算两数之和，并查某城市天气")
    print("  回合3: 考察它的历史记忆")
    print("  回合4: Ctrl+C -> 重启 -> 问它之前说了什么（断点续联）")
    print("=" * 55 + "\n")

    gateway = app.modules.channel_gateway

    if not gateway.feishu_long_connection.initialized:
        print(f"[❌ 飞书] 长连接未就绪: {gateway.feishu_long_connection.error}")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    queue: asyncio.Queue[UniversalEvent] = asyncio.Queue()

    def _on_event(event: UniversalEvent) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    async def _consume():
        while True:
            event = await queue.get()
            try:
                reply = await _execute_agent(event, app, hub, tool_descs)
                await _reply_to_feishu(event, reply)
            except Exception as e:
                print(f"[❌ 执行异常] {e}")

    async def _run():
        await asyncio.gather(
            _consume(),
            asyncio.to_thread(
                gateway.run_feishu_long_connection,
                app.config.feishu,
                _on_event,
            )
        )

    try:
        loop.run_until_complete(_run())
    except KeyboardInterrupt:
        print("\n\n[信息] 进程已被手动终止（Ctrl+C）。")
        print("       → 重新运行脚本后，在飞书发送一条消息，验证历史记忆是否能从 Redis 续接！\n")
    finally:
        loop.close()


if __name__ == "__main__":
    main()
