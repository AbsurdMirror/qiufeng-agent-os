from pathlib import Path
from typing import Annotated

from pydantic import Field

from src.qfaos import QFAConfig, QFAEnum, QFAOS


# 1. 创建 QFAOS 实例
my_agent = QFAOS()

# 2. 注册飞书渠道（example.py#L9-15），从本地文件读取 app_secret
base_dir = Path(__file__).parent
feishu_secret_path = base_dir / "feishu_secret"
feishu_secret = feishu_secret_path.read_text(encoding="utf-8").strip()

feishu_cfg = QFAConfig.Channel.Feishu(
    app_id="cli_a93a9efeb378dbd9",
    app_secret=feishu_secret,
    mode=QFAEnum.Feishu.Mode.long_connection,
)
my_agent.register_channel(QFAEnum.Channel.Feishu, feishu_cfg)

# 3. 注册模型（example.py#L17-23），从本地文件读取 api_key
minimax_api_key_path = base_dir / "minimax_api_key"
minimax_api_key = minimax_api_key_path.read_text(encoding="utf-8").strip()

minimax_cfg = QFAConfig.Model.MiniMax(
    model_name="minimax/MiniMax-M2.7",
    api_key=minimax_api_key,
    base_url="https://api.minimaxi.com/v1",
)
my_agent.register_model(QFAEnum.Model.MiniMax, minimax_cfg)

# 4. 注册安全原语（example.py#L25-39）
def send_email_action(to: str, subject: str, body: str) -> str:
    return f"sent to={to}; subject={subject}; body={body}"


def send_email_policy(to: str, _subject: str, _body: str) -> QFAEnum.Primitive.Policy:
    if to == "admin@example.com":
        return QFAEnum.Primitive.Policy.Allow
    if to.endswith("@example.com"):
        return QFAEnum.Primitive.Policy.AskTicket
    return QFAEnum.Primitive.Policy.Deny


my_agent.register_security_primitive("send_email", send_email_action, send_email_policy)

# 5. 注册工具（example.py#L41-60）
@my_agent.custom_pytool
def calculate(
    a: Annotated[int, Field(description="第一个整数")],
    b: Annotated[int, Field(description="第二个整数")],
) -> int:
    return a + b


@my_agent.custom_pytool
def send_email(
    to: Annotated[str, Field(description="收件人邮箱地址")],
    subject: Annotated[str, Field(description="邮件主题")],
    body: Annotated[str, Field(description="邮件正文")],
) -> str:
    return my_agent.primitives.send_email(to, subject, body)


my_agent.register_tool("calculate", calculate)
my_agent.register_tool("send_email", send_email)

# 6. 注册记忆策略（example.py#L62-67）
memory_cfg = QFAConfig.Memory(
    backend=QFAEnum.Memory.Backend.in_memory,
)
my_agent.register_memory(memory_cfg)

# 7. 注册观测 log 策略（example.py#L68-73，按当前 QFAConfig 接口适配）
log_cfg = QFAConfig.Observability.Log(
    jsonl_log_dir="./p05_t7_scripts_logs",
)
my_agent.register_observability_log(log_cfg)


# 8. 注册 agent 编排流程（example.py#L74-163，按当前 qfaos 接口适配）
@my_agent.custom_execute
async def execute(event, ctx) -> None:
    session_ctx = ctx.get_session_ctx(event.session_id)
    session_ctx.record(
        "demo.event.received",
        {"channel": str(event.channel), "type": str(event.type), "session_id": event.session_id, "payload": event.payload},
        level="INFO",
    )
    if event.channel != QFAEnum.Channel.Feishu or event.type != QFAEnum.Event.TextMessage:
        session_ctx.record("demo.event.ignored", {"reason": "not_text_message"}, level="DEBUG")
        return

    MAX_ROUND = 5

    if session_ctx.state.get("ticket_asked", False):
        session_ctx.record(
            "demo.ticket.resume",
            {"remaining_rounds": session_ctx.state.get("remaining_rounds"), "tool_call": session_ctx.state.get("tool_call")},
            level="INFO",
        )
        remaining_rounds = session_ctx.state.get("remaining_rounds", MAX_ROUND)
        response = await session_ctx.call_pytool(
            session_ctx.state["tool_call"],
            ticket_id=session_ctx.state["ticket"],
        )
        assert not response.is_ask_ticket
        session_ctx.state.pop("ticket", None)
        session_ctx.state.pop("tool_call", None)
        session_ctx.state.pop("remaining_rounds", None)
        session_ctx.state["ticket_asked"] = False
        prompt = f"""
        你是一个智能体"憨憨"，你的任务是根据用户的问题，调用工具来回答用户的问题。
        请根据工具调用的结果继续回答用户的问题。
        你的记忆：{await session_ctx.get_memory()}
        工具调用结果：{response.output}
        """
        await session_ctx.add_memory(str(response.output))
    else:
        session_ctx.record("demo.turn.start", {"max_round": MAX_ROUND}, level="INFO")
        prompt = f"""
        你是一个智能体"憨憨"，你的任务是根据用户的问题，调用工具来回答用户的问题。
        请根据用户的问题，调用工具来回答用户的问题。
        你的记忆：{await session_ctx.get_memory()}
        用户的问题：{event.payload}
        """
        await session_ctx.add_memory(event.payload)
        remaining_rounds = MAX_ROUND

    for i in range(remaining_rounds):
        session_ctx.record("demo.round.begin", {"round_index": i, "remaining_rounds": remaining_rounds}, level="DEBUG")
        model_output = await session_ctx.model_ask(
            minimax_cfg,
            prompt,
            tools_mode="all",
        )
        session_ctx.record(
            "demo.model.output",
            {"is_pytool_call": model_output.is_pytool_call, "is_answer": model_output.is_answer},
            level="DEBUG",
        )

        if model_output.is_pytool_call:
            session_ctx.record("demo.tool.call.begin", {"tool_call": model_output.tool_call}, level="INFO")
            response = await session_ctx.call_pytool(model_output.tool_call)
            session_ctx.record(
                "demo.tool.call.result",
                {
                    "is_ask_ticket": response.is_ask_ticket,
                    "ticket": response.ticket,
                    "tool_name": response.tool_name,
                    "tool_args": response.tool_args,
                    "output": response.output,
                },
                level="INFO",
            )
            if response.is_ask_ticket:
                resp = f"""
                申请执行工具：
                工具名称：{response.tool_name}
                工具描述：{response.tool_desc}
                工具参数：{response.tool_args}
                请确认是否执行执行该工具。yes or no
                """
                await session_ctx.send_message(QFAEnum.Channel.Feishu, resp)
                session_ctx.record("demo.ticket.asked", {"ticket": response.ticket, "tool_name": response.tool_name}, level="INFO")
                session_ctx.state.clear()
                session_ctx.state.update({
                    "ticket_asked": True,
                    "ticket": response.ticket,
                    "tool_call": model_output.tool_call,
                    "remaining_rounds": MAX_ROUND - i - 1,
                })
                break
            prompt = f"""
            你是一个智能体"憨憨"，你的任务是根据用户的问题，调用工具来回答用户的问题。
            请根据工具调用的结果继续回答用户的问题。
            你的记忆：{await session_ctx.get_memory()}
            工具调用结果：{response.output}
            """
            await session_ctx.add_memory(str(response.output))
        elif model_output.is_answer:
            response_text = model_output.response or ""
            session_ctx.record("demo.answer.final", {"text_len": len(response_text)}, level="INFO")
            await session_ctx.add_memory(response_text)
            await session_ctx.send_message(QFAEnum.Channel.Feishu, response_text)
            session_ctx.state.clear()
            session_ctx.state.update({"ticket_asked": False})
            break
    else:
        resp = f"agent工具调用次数达到上限{MAX_ROUND}"
        session_ctx.record("demo.round.exhausted", {"max_round": MAX_ROUND}, level="INFO")
        await session_ctx.send_message(QFAEnum.Channel.Feishu, resp)


my_agent.run()
