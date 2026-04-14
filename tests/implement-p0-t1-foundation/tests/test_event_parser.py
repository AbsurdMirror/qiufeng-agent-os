import pytest
import json
from src.channel_gateway.parsers.text_event_parser import TextEventParserFactory
from src.channel_gateway.domain.events import UniversalTextEvent

def get_base_payload(event_type="im.message.receive_v1", message_type="text", text_content="hello test"):
    return {
        "schema": "2.0",
        "header": {
            "event_id": "evt_123",
            "event_type": event_type,
            "create_time": "1600000000000"
        },
        "event": {
            "message": {
                "message_type": message_type,
                "content": json.dumps({"text": text_content}) if message_type == "text" else "{}",
                "message_id": "msg_456",
                "chat_id": "chat_789"
            },
            "sender": {
                "sender_id": {
                    "open_id": "ou_abc"
                }
            }
        }
    }

def test_cg_02_webhook_parse_valid_text_event():
    """测试项 CG-02: Webhook模式解析合法文本消息"""
    parser = TextEventParserFactory.get("feishu", "webhook")
    payload = get_base_payload()
    event = parser.parse(payload)
    
    assert isinstance(event, UniversalTextEvent)
    assert event.platform_type == "feishu"
    assert event.text == "hello test"
    assert len(event.contents) == 1
    assert event.contents[0].type == "text"
    assert event.contents[0].data == "hello test"

def test_cg_03_long_connection_parse_valid_text_event():
    """测试项 CG-03: 长连接模式解析合法文本消息"""
    parser = TextEventParserFactory.get("feishu", "long_connection")
    payload = get_base_payload()
    event = parser.parse(payload)
    
    assert isinstance(event, UniversalTextEvent)
    assert event.platform_type == "feishu"
    assert event.text == "hello test"
    assert len(event.contents) == 1
    assert event.contents[0].type == "text"
    assert event.contents[0].data == "hello test"

def test_cg_04_factory_get_unsupported_parser():
    """测试项 CG-04: 工厂模式获取不支持的解析器"""
    with pytest.raises(ValueError, match="unsupported_event_parser"):
        TextEventParserFactory.get("feishu", "unknown_transport")
        
    with pytest.raises(ValueError, match="unsupported_event_parser"):
        TextEventParserFactory.get("unknown_channel", "webhook")

def test_cg_05_webhook_unsupported_message_type():
    """测试项 CG-05: Webhook异常处理：非文本类型"""
    parser = TextEventParserFactory.get("feishu", "webhook")
    payload = get_base_payload(message_type="image")
    with pytest.raises(ValueError, match="unsupported_message_type"):
        parser.parse(payload)

def test_cg_06_webhook_unsupported_event_type():
    """测试项 CG-06: Webhook异常处理：不支持的事件"""
    parser = TextEventParserFactory.get("feishu", "webhook")
    payload = get_base_payload(event_type="im.chat.member.bot.added_v1")
    with pytest.raises(ValueError, match="unsupported_event_type"):
        parser.parse(payload)
