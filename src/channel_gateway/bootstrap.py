from typing import Any

from src.app.settings_store import FeishuSettings
from src.channel_gateway.exports import ChannelGatewayExports
from src.channel_gateway.feishu_long_connection import (
    initialize_feishu_long_connection,
    parse_feishu_long_connection_event,
    run_feishu_long_connection,
)
from src.channel_gateway.feishu_sender import FeishuAsyncSender
from src.channel_gateway.feishu_webhook import FeishuWebhookResult, receive_feishu_webhook
from src.channel_gateway.nonebot_runtime import initialize_nonebot2
from src.channel_gateway.session_context import session_context_controller

def initialize(host: str, port: int, feishu_settings: FeishuSettings | None = None) -> ChannelGatewayExports:
    """
    渠道适配层 (Channel Gateway) 的初始化引导函数。
    
    此函数会被 `src.app.bootstrap` 在应用启动时调用。它负责：
    1. 初始化底层的机器人框架（如 NoneBot2）并绑定网络监听地址。
    2. 探测并初始化特定渠道（如飞书长连接 SDK）的运行环境。
    3. 收集并暴露所有与渠道事件相关的“入口函数”和“解析器”，
       供上层（如 App 层的长连接 runner 或 webhook server）调用。
       
    Args:
        host: NoneBot2 需要绑定的主机地址
        port: NoneBot2 需要绑定的端口
        feishu_settings: 飞书应用配置，用于初始化发送器
        
    Returns:
        ChannelGatewayExports: 包含该层所有关键实例和方法引用的强类型数据类
    """
    if feishu_settings:
        feishu_sender = FeishuAsyncSender(
            app_id=feishu_settings.app_id, 
            app_secret=feishu_settings.app_secret,
            mock_mode=False
        )
    else:
        feishu_sender = FeishuAsyncSender(mock_mode=True)

    return ChannelGatewayExports(
        layer="channel_gateway",
        status="initialized",
        nonebot2=initialize_nonebot2(host=host, port=port),
        feishu_long_connection=initialize_feishu_long_connection(),
        feishu_long_connection_parser=parse_feishu_long_connection_event,
        run_feishu_long_connection=run_feishu_long_connection,
        feishu_webhook_entry=_webhook_entry,
        feishu_sender=feishu_sender,
        # T4 新增：利用导出口（Exports）统一对外暴露出刚才实例化的全局单例 session_context_controller
        # 这就相当于给外面的老总们（编排引擎等模块）配了直接查户口的接口，免得乱 import
        session_context=session_context_controller,
    )


def _webhook_entry(payload: dict[str, Any]) -> FeishuWebhookResult:
    """
    对底层 `receive_feishu_webhook` 的一层薄封装。
    确保传递给上层（如 `webhook_server`）的是一个签名稳定的函数对象。
    """
    return receive_feishu_webhook(payload)
