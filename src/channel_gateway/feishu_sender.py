import json
import logging
import time
from typing import Any

import httpx

from src.channel_gateway.responses import ReplyText, ReplyPrimitive
from src.channel_gateway.events import UniversalEvent

# ============================================================
# 渠道适配层 —— 飞书异步消息发送器 (Feishu Async Message Sender)
#
# 本模块实现了规格 GW-P0-08（异步接口）和 GW-P0-09（渠道适配）。
# 
# 重构记录 (T5 阶段):
#   已从虚假的 mock 实现重构为真实的飞书开放平台 API 调用实现。
#   完全采用 httpx.AsyncClient 进行非阻塞的异步网络请求，并内置了
#   对 tenant_access_token 的拉取与 TTL 缓存机制。
# ============================================================

logger = logging.getLogger(__name__)

class FeishuAsyncSender:
    """
    飞书通道的真实异步消息发送器 (Feishu Async Message Sender)。

    设计意图 (GW-P0-08, GW-P0-09)：
        提供原生的异步 HTTP 回传接口，将渠道层的响应原语投递到飞书用户或群聊。
        绝不使用任何阻塞事件循环的同步网络库。

    Args:
        app_id (str): 飞书自建应用的 App ID
        app_secret (str): 飞书自建应用的 App Secret
        mock_mode (bool): 如果为 True，则不发送真实网络请求，仅打印日志（方便测试）。
    """

    def __init__(self, app_id: str = "", app_secret: str = "", mock_mode: bool = False):
        self.app_id = app_id
        self.app_secret = app_secret
        self.mock_mode = mock_mode
        
        # httpx 异步客户端生命周期管理，复用连接池以提高并发性能
        self._client = httpx.AsyncClient(timeout=10.0)
        
        # Token 缓存相关
        self._tenant_access_token: str | None = None
        self._token_expire_time: float = 0.0

        if self.mock_mode:
            logger.info("FeishuAsyncSender initialized in mock mode.")
        else:
            if not self.app_id or not self.app_secret:
                logger.warning("FeishuAsyncSender initialized without app_id or app_secret! Network calls will fail.")

    async def _get_tenant_access_token(self) -> str:
        """
        获取或刷新 tenant_access_token。
        带有内存 TTL 缓存机制，避免频繁拉取。
        """
        if self._tenant_access_token and time.time() < self._token_expire_time:
            return self._tenant_access_token

        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        
        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") != 0:
                raise RuntimeError(f"Feishu Auth API Error: {data.get('msg')}")
                
            self._tenant_access_token = data.get("tenant_access_token")
            # 飞书通常返回 expire=7200 (秒)。为了安全起见，我们提前 5 分钟 (300 秒) 让其过期刷新
            expire_seconds = data.get("expire", 7200)
            self._token_expire_time = time.time() + expire_seconds - 300
            
            return self._tenant_access_token
            
        except httpx.RequestError as e:
            logger.error(f"Network error while fetching Feishu tenant token: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to fetch Feishu tenant token: {e}")
            raise

    async def send_text_reply(self, reply: ReplyText, target_event: UniversalEvent) -> dict[str, Any]:
        """
        向飞书投递纯文本回复消息（异步）。
        """
        # 1. 构造路由 ID 和类型
        # 对应 [REV-GW0809-CON-002+BUG-001]
        # 根据事件来源动态决定发给群聊还是单聊。如果不做动态切换，群聊里艾特机器人的消息
        # 机器人会以"私聊"形式回复那个人，导致群里其他人看不到。
        if target_event.group_id:
            receive_id = target_event.group_id
            receive_id_type = "chat_id"  # 飞书 API 规定的群聊身份标识
        else:
            receive_id = target_event.user_id
            receive_id_type = "open_id"  # 飞书 API 规定的个人身份标识

        # 2. 构造消息载荷
        # 注意：飞书 API 规范要求，当 msg_type 为 text 时，content 必须是被转义的 JSON 字符串
        content_str = json.dumps({"text": reply.content}, ensure_ascii=False)
        
        payload = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": content_str,
            "reply_to": target_event.message_id
        }

        if self.mock_mode:
            logger.info(f"[MOCK FEISHU SEND] type={receive_id_type} Payload: {payload}")
            return {"status": "success", "mock": True, "payload": payload}

        # 3. 真实发送模式
        try:
            token = await self._get_tenant_access_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8"
            }
            url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={receive_id_type}"
            
            response = await self._client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") != 0:
                logger.error(f"Feishu Send Message API returned error: {data}")
                return {"status": "failed", "error": data}
                
            return {"status": "success", "data": data.get("data")}
            
        except httpx.RequestError as e:
            logger.error(f"Network error while sending message to Feishu: {e}")
            return {"status": "failed", "error": str(e)}
        except Exception as e:
            logger.error(f"Failed to send message to Feishu: {e}")
            return {"status": "failed", "error": str(e)}

    async def send_card_reply(self, reply: ReplyPrimitive, target_event: UniversalEvent) -> dict[str, Any]:
        """
        向飞书投递消息卡片（异步占位）。
        """
        raise NotImplementedError("Feishu card sending is not implemented yet.")

    async def aclose(self):
        """
        优雅关闭内部的 httpx 异步连接池。
        """
        await self._client.aclose()
