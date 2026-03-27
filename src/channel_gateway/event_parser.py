from collections.abc import Mapping
import json
from typing import Any, Protocol

from src.channel_gateway.events import UniversalEvent, UniversalEventContent


class TextEventParser(Protocol):
    """
    事件解析器接口协议 (Duck Typing)。
    所有的渠道事件解析器都必须实现 parse 方法，将原始字典载荷转换为 UniversalEvent。
    """
    def parse(self, payload: Mapping[str, Any]) -> UniversalEvent: ...


class FeishuWebhookTextEventParser:
    """飞书 Webhook 模式的事件解析策略。"""
    def parse(self, payload: Mapping[str, Any]) -> UniversalEvent:
        # Webhook 模式下，事件被包裹在 header 和 event 中
        header = _require_mapping(payload, "header")
        event = _require_mapping(payload, "event")
        message = _require_mapping(event, "message")
        sender = _require_mapping(event, "sender")
        sender_id = _require_mapping(sender, "sender_id")

        message_type = _require_str(message, "message_type")
        if message_type != "text":
            raise ValueError("unsupported_message_type")

        event_type = _optional_str(header, "event_type")
        if event_type is not None and event_type != "im.message.receive_v1":
            raise ValueError("unsupported_event_type")

        # 解析被二次序列化的 content 字符串
        content = _require_str(message, "content")
        content_payload = _load_json_dict(content)
        text = content_payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("empty_text")

        timestamp = _parse_timestamp(_require_str(header, "create_time"))
        user_id = _extract_user_id(sender_id)
        chat_id = _optional_str(message, "chat_id")
        
        # 将解析出的文本包装进支持多模态的 UniversalEventContent
        contents = (UniversalEventContent(type="text", data=text),)
        
        return UniversalEvent(
            event_id=_require_str(header, "event_id"),
            timestamp=timestamp,
            platform_type="feishu",
            user_id=user_id,
            group_id=chat_id,
            room_id=chat_id,
            message_id=_require_str(message, "message_id"),
            contents=contents,
            raw_event=dict(payload),
        )


class FeishuLongConnectionTextEventParser:
    """飞书 WebSocket 长连接模式的事件解析策略。"""
    def parse(self, payload: Mapping[str, Any]) -> UniversalEvent:
        # 长连接模式下，事件没有外层的 schema 包装，直接暴露 header 和 event
        header = _require_mapping(payload, "header")
        event = _require_mapping(payload, "event")
        message = _require_mapping(event, "message")
        sender = _require_mapping(event, "sender")
        sender_id = _require_mapping(sender, "sender_id")

        event_type = _require_str(header, "event_type")
        if event_type != "im.message.receive_v1":
            raise ValueError("unsupported_event_type")

        message_type = _require_str(message, "message_type")
        if message_type != "text":
            raise ValueError("unsupported_message_type")

        content = _require_str(message, "content")
        content_payload = _load_json_dict(content)
        text = content_payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("empty_text")

        timestamp = _parse_timestamp(_require_str(header, "create_time"))
        user_id = _extract_user_id(sender_id)
        chat_id = _optional_str(message, "chat_id")
        
        contents = (UniversalEventContent(type="text", data=text),)

        return UniversalEvent(
            event_id=_require_str(header, "event_id"),
            timestamp=timestamp,
            platform_type="feishu",
            user_id=user_id,
            group_id=chat_id,
            room_id=chat_id,
            message_id=_require_str(message, "message_id"),
            contents=contents,
            raw_event=dict(payload),
        )


class TextEventParserFactory:
    """
    事件解析器工厂。
    使用策略模式，根据渠道 (channel) 和传输方式 (transport) 返回对应的解析器实例。
    这种设计对未来扩展钉钉、微信等新渠道完全开放。
    """
    _registry: dict[tuple[str, str], TextEventParser] = {
        ("feishu", "webhook"): FeishuWebhookTextEventParser(),
        ("feishu", "long_connection"): FeishuLongConnectionTextEventParser(),
    }

    @classmethod
    def get(cls, channel: str, transport: str) -> TextEventParser:
        """
        获取指定渠道和传输方式的解析器。
        
        Args:
            channel: 渠道名称，例如 "feishu"
            transport: 传输模式，例如 "webhook" 或 "long_connection"
            
        Returns:
            TextEventParser: 对应的解析器实例
            
        Raises:
            ValueError: 若请求的解析器未注册，则抛出异常
        """
        parser = cls._registry.get((channel, transport))
        if parser is None:
            raise ValueError("unsupported_event_parser")
        return parser


def _require_mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    nested = value.get(key)
    if not isinstance(nested, Mapping):
        raise ValueError(f"missing_{key}")
    return nested


def _require_str(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(f"missing_{key}")
    return item


def _optional_str(value: Mapping[str, Any], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str):
        raise ValueError(f"invalid_{key}")
    return item


def _parse_timestamp(value: str) -> int:
    try:
        return int(value)
    except ValueError as error:
        raise ValueError("invalid_timestamp") from error


def _extract_user_id(sender_id: Mapping[str, Any]) -> str:
    user_id = sender_id.get("open_id")
    if not isinstance(user_id, str) or not user_id:
        raise ValueError("missing_user_id")
    return user_id


def _load_json_dict(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("invalid_message_content") from error
    if not isinstance(parsed, dict):
        raise ValueError("invalid_message_content")
    return parsed
