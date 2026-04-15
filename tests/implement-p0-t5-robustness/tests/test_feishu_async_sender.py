import asyncio
import json
import time

import pytest

from src.channel_gateway.core.domain.events import UniversalEvent, UniversalEventContent
from src.channel_gateway.channels.feishu.sender import FeishuAsyncSender
from src.channel_gateway.core.domain.responses import ReplyText


def _make_event(*, group_id: str | None) -> UniversalEvent:
    return UniversalEvent(
        event_id="evt_1",
        timestamp=int(time.time() * 1000),
        platform_type="feishu",
        user_id="ou_user_1",
        group_id=group_id,
        room_id=None,
        message_id="msg_1",
        contents=(UniversalEventContent(type="text", data="hello"),),
        raw_event={"raw": True},
        logical_uid="uid_1",
    )


def test_gw_t5_01_reply_text_rejects_empty_content():
    """测试项 GW-T5-01: ReplyText 空内容防御"""
    with pytest.raises(ValueError, match="cannot be empty"):
        ReplyText(content="")


def test_gw_t5_02_sender_route_switches_between_group_and_user():
    """测试项 GW-T5-02: 群聊/私聊路由选择"""
    sender = FeishuAsyncSender(mock_mode=True)

    group_event = _make_event(group_id="oc_chat_1")
    user_event = _make_event(group_id=None)

    result_group = asyncio.run(sender.send_text_reply(ReplyText(content="hi"), group_event))
    result_user = asyncio.run(sender.send_text_reply(ReplyText(content="hi"), user_event))

    assert result_group["status"] == "success"
    assert result_group["payload"]["receive_id"] == "oc_chat_1"
    assert result_group["payload"]["reply_to"] == "msg_1"

    assert result_user["status"] == "success"
    assert result_user["payload"]["receive_id"] == "ou_user_1"
    assert result_user["payload"]["reply_to"] == "msg_1"


def test_gw_t5_03_sender_splits_long_text_and_only_first_chunk_has_reply_to():
    """测试项 GW-T5-03: 长文本分片与 reply_to 规则"""
    sender = FeishuAsyncSender(mock_mode=True)
    event = _make_event(group_id="oc_chat_1")

    long_text = "A" * 9001
    result = asyncio.run(sender.send_text_reply(ReplyText(content=long_text), event))

    assert result["status"] == "success"
    payload = result["payload"]
    content_obj = json.loads(payload["content"])
    assert len(content_obj["text"]) == 1001
    assert set(content_obj["text"]) == {"A"}


def test_gw_t5_03b_first_chunk_has_reply_to_followed_by_plain_messages(monkeypatch):
    sender = FeishuAsyncSender(app_id="id", app_secret="sec", mock_mode=False)
    event = _make_event(group_id="oc_chat_1")

    sent_payloads: list[dict] = []

    async def fake_get_token():
        return "token"

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"code": 0, "data": {"message_id": "m"}}

    async def fake_post(url, headers=None, json=None):
        sent_payloads.append({"url": url, "headers": headers, "json": json})
        return _Resp()

    monkeypatch.setattr(sender, "_get_tenant_access_token", fake_get_token)
    monkeypatch.setattr(sender._client, "post", fake_post)

    long_text = "B" * 9001
    result = asyncio.run(sender.send_text_reply(ReplyText(content=long_text), event))

    assert result["status"] == "success"
    assert len(sent_payloads) == 3
    assert sent_payloads[0]["json"]["reply_to"] == "msg_1"
    assert "reply_to" not in sent_payloads[1]["json"]
    assert "reply_to" not in sent_payloads[2]["json"]


def test_gw_t5_04_tenant_access_token_ttl_cache(monkeypatch):
    """测试项 GW-T5-04: tenant_access_token TTL 缓存"""
    sender = FeishuAsyncSender(app_id="id", app_secret="sec", mock_mode=False)
    calls: list[dict] = []

    class _Resp:
        def __init__(self, token: str, expire: int):
            self._token = token
            self._expire = expire

        def raise_for_status(self):
            return None

        def json(self):
            return {"code": 0, "tenant_access_token": self._token, "expire": self._expire}

    async def fake_post(url, json=None, headers=None):
        calls.append({"url": url, "json": json, "headers": headers})
        return _Resp(token=f"t{len(calls)}", expire=7200)

    monkeypatch.setattr(sender._client, "post", fake_post)

    token1 = asyncio.run(sender._get_tenant_access_token())
    token2 = asyncio.run(sender._get_tenant_access_token())

    assert token1 == token2
    assert len(calls) == 1
