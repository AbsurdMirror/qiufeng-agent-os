from typing import Annotated

from pydantic import Field

from qfaos import QFAOS, QFAConfig, QFAEnum

my_agent = QFAOS()

# 注册channel（P0 基础上更贴近现状：飞书长连接只需要 app_id / app_secret；Webhook 相关参数独立）
feishu_cfg = QFAConfig.Channel.Feishu(
    app_id="123456",
    app_secret="123456",
    mode=QFAEnum.Feishu.Mode.long_connection,
)
my_agent.register_channel(QFAEnum.Channel.Feishu, feishu_cfg)

# 注册模型（P0 基础上更贴近现状：以 api_key/base_url/model_name 作为最小信息）
minimax_cfg = QFAConfig.Model.MiniMax(
    model_name="MiniMax-Text-01",
    api_key="123456",
    base_url="https://api.minimax.chat/v1",
)
my_agent.register_model(QFAEnum.Model.MiniMax, minimax_cfg)

# 注册安全原语（示例：自定义业务原语 + 策略；策略允许返回 Allow / Deny / AskTicket）
def send_email_action(to: str, subject: str, body: str) -> str:
    """发送邮件"""
    import a_package_with_email
    return a_package_with_email.send_email(to, subject, body)

def send_email_policy(to: str, _subject: str, _body: str) -> QFAEnum.Primitive.Policy:
    """发送邮件"""
    if to == "admin@example.com":
        return QFAEnum.Primitive.Policy.Allow
    if to.endswith("@example.com"):
        return QFAEnum.Primitive.Policy.AskTicket
    return QFAEnum.Primitive.Policy.Deny

my_agent.register_security_primitive("send_email", send_email_action, send_email_policy)

# 注册工具（Pydantic v2 + tool spec 解析友好写法：Annotated[T, Field(...)]）
@my_agent.custom_pytool
def calculate(
    a: Annotated[int, Field(description="第一个整数")],
    b: Annotated[int, Field(description="第二个整数")],
) -> int:
    """计算两个整数的和"""
    return a + b

@my_agent.custom_pytool
def send_email(
    to: Annotated[str, Field(description="收件人邮箱地址")],
    subject: Annotated[str, Field(description="邮件主题")],
    body: Annotated[str, Field(description="邮件正文")],
) -> str:
    """发送邮件"""
    return my_agent.primitives.send_email(to, subject, body)

my_agent.register_tool("calculate", calculate)
my_agent.register_tool("send_email", send_email)

# 注册记忆策略
memory_cfg = QFAConfig.Memory(
    backend=QFAEnum.Memory.Backend.in_memory
)
my_agent.register_memory(memory_cfg)

# 注册观测log策略
log_cfg = QFAConfig.Observability.Log(
    log_level=QFAEnum.Observability.LogLevel.INFO
)
my_agent.register_observability_log(log_cfg)

# 注册agent编排流程（示例：以“对话 + 工具调用 + 票据审批”方式编排；具体实现由 app 层封装六层能力）
@my_agent.custom_execute
async def execute(
        event,
        ctx
    ) -> None:
    """执行智能体编排流程"""
    # 目标：让用户只写“业务编排”，把工具列表注入、记忆注入、票据恢复、消息发送等通用流程交给 qfaos SDK 托底。
    if event.channel != QFAEnum.Channel.Feishu or event.type != QFAEnum.Event.TextMessage:
        return

    session_ctx = ctx.get_session_ctx(event.session_id)

    
    MAX_ROUND = 5
    if session_ctx.custom_data.get("ticket_asked", False):
        session_ctx.add_ticket(session_ctx.custom_data["ticket"])
        response = session_ctx.call_pytool(session_ctx.custom_data["tool_call"])
        assert not response.is_ask_ticket
        prompt = f"""
        你是一个智能体，你的任务是根据用户的问题，调用工具来回答用户的问题。
        请根据工具调用的结果继续回答用户的问题。
        你的工具列表：{ctx.get_all_tools()}
        你的记忆：{session_ctx.get_memory()}
        工具调用结果：{response.output}
        """
        session_ctx.add_memory(response.output)
        remaining_rounds = session_ctx.custom_data["remaining_rounds"]
    else:
        prompt = f"""
        你是一个智能体，你的任务是根据用户的问题，调用工具来回答用户的问题。
        请根据用户的问题，调用工具来回答用户的问题。
        你的工具列表：{ctx.get_all_tools()}
        你的记忆：{session_ctx.get_memory()}
        用户的问题：{event.payload}
        """
        session_ctx.add_memory(event.payload)
        remaining_rounds = MAX_ROUND
    
    for i in range(remaining_rounds):
        model_output = await session_ctx.model_ask(QF_Enum.Model.Minimax, prompt)

        if model_output.is_pytool_call:
            # 调用工具
            response = session_ctx.call_pytool(model_output.tool_call)
            if response.is_ask_ticket:
                # 询问用户ticket许可
                resp = f"""
                申请执行工具：
                工具名称：{response.tool_name}
                工具描述：{response.tool_desc}
                工具参数：{response.tool_args}
                请确认是否执行执行该工具。yes or no
                """
                session_ctx.send_message(QF_Enum.Channel.Feishu, resp)
                # 保存上下文
                session_ctx.custom_data = {
                    "ticket_asked": True,
                    "ticket": response.ticket,
                    "tool_call": response.tool_call,
                    "remaining_rounds": MAX_ROUND - i - 1, #剩余round次数
                }
                break
            else:
                prompt = f"""
                你是一个智能体，你的任务是根据用户的问题，调用工具来回答用户的问题。
                请根据工具调用的结果继续回答用户的问题。
                你的工具列表：{ctx.get_all_tools()}
                你的记忆：{session_ctx.get_memory()}
                工具调用结果：{response.output}
                """
                session_ctx.add_memory(response.output)
        elif model_output.is_answer:
            # 回答用户问题
            response = model_output.response
            session_ctx.add_memory(response)
            session_ctx.send_message(QF_Enum.Channel.Feishu, response)
            # 保存上下文
            session_ctx.custom_data = {
                "ticket_asked": False,
            }
            break

        i += 1
    
    resp = f"""
    agent工具调用次数达到上限{MAX_ROUND}
    """
    session_ctx.send_message(QF_Enum.Channel.Feishu, resp)


my_agent.run()
