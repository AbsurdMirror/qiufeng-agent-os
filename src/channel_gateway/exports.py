from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.app.settings_store import FeishuSettings
from src.channel_gateway.domain.events import UniversalEvent
from src.channel_gateway.transports.feishu.long_connection import FeishuLongConnectionRuntime
from src.channel_gateway.transports.feishu.webhook import FeishuWebhookResult
from src.channel_gateway.senders.feishu_async_sender import FeishuAsyncSender
from src.channel_gateway.core.nonebot_runtime import NoneBotRuntime
from src.channel_gateway.session.context import SessionContextController

@dataclass(frozen=True)
class ChannelGatewayExports:
    layer: str
    status: str
    nonebot2: NoneBotRuntime
    feishu_long_connection: FeishuLongConnectionRuntime
    feishu_long_connection_parser: Callable[[dict[str, Any]], UniversalEvent]
    run_feishu_long_connection: Callable[
        [FeishuSettings, Callable[[UniversalEvent], None]],
        None,
    ]
    feishu_webhook_entry: Callable[[dict[str, Any]], FeishuWebhookResult]
    feishu_sender: FeishuAsyncSender
    session_context: SessionContextController
