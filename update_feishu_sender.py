with open("src/channel_gateway/feishu_sender.py", "r") as f:
    content = f.read()

# Replace ReplyText with ReplyPrimitive in typing
content = content.replace(
    "from src.channel_gateway.responses import ReplyText",
    "from src.channel_gateway.responses import ReplyText, ReplyPrimitive"
)

# Update send_text_reply
search_text = """
    async def send_text_reply(self, reply: ReplyText, target_event: UniversalEvent) -> dict[str, Any]:
        \"\"\"
        向飞书投递纯文本回复消息（异步）。

        Args:
            reply (ReplyText): 纯文本响应原语，包含要发送的文本内容。
            target_event (UniversalEvent): 触发本次回复的原始事件。
                用于从中提取收件目标（user_id / message_id），
                确保回复精准发送给原始发言人，并关联到原始消息线程。

        Returns:
            dict[str, Any]: mock 模式下返回模拟的成功响应字典；
                            真实模式下应返回飞书 API 的 HTTP 响应体（待实现）。

        Raises:
            NotImplementedError: 当 mock_mode=False 时抛出，提示真实发送逻辑尚未实现。

        风险提示：
            当前 payload 缺少飞书必需字段 receive_id_type（如 "open_id"），
            真实模式下调用飞书 API 将会报错。详见审阅报告 [REV-GW0809-BUG-001]。
        \"\"\"
        # 构造向飞书发送的消息载荷
        # receive_id: 收件人 ID，这里使用事件发送者的 user_id 作为回复目标
        # TODO: 群聊场景应使用 target_event.group_id 而非 user_id
        # TODO: 真实飞书 API 还需要额外传入 receive_id_type 字段（如 "open_id"）
        payload = {
            "receive_id": target_event.user_id,  # 注意：群聊时应改用 group_id，详见审阅报告
            "msg_type": "text",                   # 消息类型固定为纯文本
            "content": {"text": reply.content},   # 真正的文本内容，来自响应原语
            "reply_to": target_event.message_id   # 关联原消息 ID，飞书将以回复线程形式展示
        }
"""

replace_text = """
    async def send_text_reply(self, reply: ReplyPrimitive, target_event: UniversalEvent) -> dict[str, Any]:
        \"\"\"
        向飞书投递纯文本回复消息（异步）。

        Args:
            reply (ReplyPrimitive): 纯文本响应原语，包含要发送的文本内容。
            target_event (UniversalEvent): 触发本次回复的原始事件。
                用于从中提取收件目标（user_id / message_id），
                确保回复精准发送给原始发言人，并关联到原始消息线程。

        Returns:
            dict[str, Any]: mock 模式下返回模拟的成功响应字典；
                            真实模式下应返回飞书 API 的 HTTP 响应体（待实现）。

        Raises:
            NotImplementedError: 当 mock_mode=False 时抛出，提示真实发送逻辑尚未实现。
        \"\"\"
        # 构造向飞书发送的消息载荷
        receive_id_type = "chat_id" if target_event.group_id else "open_id"
        receive_id = target_event.group_id if target_event.group_id else target_event.user_id

        payload = {
            "receive_id": receive_id,
            "receive_id_type": receive_id_type,
            "msg_type": "text",
            "content": '{"text": "' + reply.content.replace('"', '\\\\"') + '"}',
            "reply_to": target_event.message_id
        }
"""
content = content.replace(search_text, replace_text)

# Add send_card_reply placeholder
card_reply_code = """
    async def send_card_reply(self, reply: ReplyPrimitive, target_event: UniversalEvent) -> dict[str, Any]:
        \"\"\"
        向飞书投递卡片回复消息（异步）占位。
        \"\"\"
        receive_id_type = "chat_id" if target_event.group_id else "open_id"
        receive_id = target_event.group_id if target_event.group_id else target_event.user_id

        payload = {
            "receive_id": receive_id,
            "receive_id_type": receive_id_type,
            "msg_type": "interactive",
            "content": "{}", # Placeholder for card content
            "reply_to": target_event.message_id
        }

        if self.mock_mode:
            logger.info(f"[MOCK FEISHU SEND CARD] Payload: {payload}")
            return {"status": "success", "mock": True, "payload": payload}
        else:
            raise NotImplementedError("Real Feishu network sending is not implemented yet.")
"""

content += card_reply_code

with open("src/channel_gateway/feishu_sender.py", "w") as f:
    f.write(content)
