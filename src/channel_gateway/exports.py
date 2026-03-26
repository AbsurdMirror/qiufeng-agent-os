from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.app.settings_store import FeishuSettings
from src.channel_gateway.events import UniversalTextEvent
from src.channel_gateway.feishu_long_connection import FeishuLongConnectionRuntime
from src.channel_gateway.feishu_webhook import FeishuWebhookResult
from src.channel_gateway.nonebot_runtime import NoneBotRuntime


@dataclass(frozen=True)
class ChannelGatewayExports:
    layer: str
    status: str
    nonebot2: NoneBotRuntime
    feishu_long_connection: FeishuLongConnectionRuntime
    feishu_long_connection_parser: Callable[[dict[str, Any]], UniversalTextEvent]
    run_feishu_long_connection: Callable[
        [FeishuSettings, Callable[[UniversalTextEvent], None]],
        None,
    ]
    feishu_webhook_entry: Callable[[dict[str, Any]], FeishuWebhookResult]
