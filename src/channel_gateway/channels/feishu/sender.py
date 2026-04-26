import json
import logging
import time
import os
from pathlib import Path
from typing import Any

import httpx

from src.domain.responses import ReplyPrimitive, ReplyText, FeishuReplyCard
from src.domain.events import UniversalEvent

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
        # 飞书文本消息有长度限制（单次最多约 4000 字符）。
        # 如果超出限制，我们需要分片发送以防止直接抛错 (T5 审阅 P1)
        full_content = reply.content
        max_chunk_size = 4000
        
        # 将内容切分为大小不超过 max_chunk_size 的多个块
        # 这里的切片方案保证了大模型在输出超长推理过程或巨型代码块时，
        # 用户依然能像看连载小说一样完整接收所有信息，而不是静默丢失。
        chunks = [full_content[i:i+max_chunk_size] for i in range(0, len(full_content), max_chunk_size)]
        
        last_result = None
        for i, chunk in enumerate(chunks):
            # 只有第一个 chunk 保留 reply_to 关系，后续的 chunk 直接发
            # 保证群聊回复时，只有第一段会显示"回复某某的某条消息"，后续段落作为普通新消息追加
            current_reply_to = target_event.message_id if i == 0 else None
            
            content_str = json.dumps({"text": chunk}, ensure_ascii=False)
            
            payload = {
                "receive_id": receive_id,
                "msg_type": "text",
                "content": content_str,
            }
            if current_reply_to:
                payload["reply_to"] = current_reply_to
    
            if self.mock_mode:
                logger.info(f"[MOCK FEISHU SEND] type={receive_id_type} Chunk {i+1}/{len(chunks)} Payload: {payload}")
                last_result = {"status": "success", "mock": True, "payload": payload}
                continue
    
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
                    logger.error(f"Feishu Send Message API returned error on chunk {i+1}: {data}")
                    # 如果某一块发送失败，直接中断并返回错误
                    return {"status": "failed", "error": data, "chunk_index": i}
                    
                last_result = {"status": "success", "data": data.get("data")}
                
            except httpx.RequestError as e:
                logger.error(f"Network error while sending message chunk {i+1} to Feishu: {e}")
                return {"status": "failed", "error": str(e), "chunk_index": i}
            except Exception as e:
                logger.error(f"Failed to send message chunk {i+1} to Feishu: {e}")
                return {"status": "failed", "error": str(e), "chunk_index": i}
                
        return last_result or {"status": "failed", "error": "Empty message chunks"}

    async def send_feishu_card_reply(self, reply: FeishuReplyCard, target_event: UniversalEvent) -> dict[str, Any]:
        """
        向飞书投递消息卡片（异步）。
        对应规格 GW-P0-09 以及飞书卡片模板发送流程。
        """
        # 1. 构造路由 ID 和类型
        if target_event.group_id:
            receive_id = target_event.group_id
            receive_id_type = "chat_id"
        else:
            receive_id = target_event.user_id
            receive_id_type = "open_id"

        # 2. 构造卡片载荷
        card_content = {
            "type": "template",
            "data": {
                "template_id": reply.template_id,
                "template_variable": reply.template_variable
            }
        }

        payload = {
            "receive_id": receive_id,
            "msg_type": "interactive",
            "content": json.dumps(card_content, ensure_ascii=False),
        }
        
        # 支持回复特定消息
        if target_event.message_id:
            payload["reply_to"] = target_event.message_id

        if self.mock_mode:
            logger.info(f"[MOCK FEISHU CARD SEND] type={receive_id_type} Template={reply.template_id} Payload: {payload}")
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
                logger.error(f"Feishu Send Card API returned error: {data}")
                return {"status": "failed", "error": data}
                
            return {"status": "success", "data": data.get("data")}
            
        except httpx.RequestError as e:
            logger.error(f"Network error while sending card to Feishu: {e}")
            return {"status": "failed", "error": str(e)}
        except Exception as e:
            logger.error(f"Failed to send card to Feishu: {e}")
            return {"status": "failed", "error": str(e)}

    async def download_image(self, message_id: str, file_key: str) -> str:
        """
        从飞书下载图片并保存到本地临时目录。
        返回本地文件绝对路径。
        """
        temp_dir = Path("data/temp_images")
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = temp_dir / f"{file_key}.jpg"
        
        if self.mock_mode:
            logger.info(f"[MOCK FEISHU DOWNLOAD] message_id={message_id}, file_key={file_key} -> {file_path}")
            # 创建一个虚假的空文件用于测试
            file_path.touch()
            return str(file_path.absolute())

        try:
            token = await self._get_tenant_access_token()
            headers = {
                "Authorization": f"Bearer {token}"
            }
            # 飞书获取消息资源接口 (获取消息中的资源文件)
            # 文档: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message-resource/get
            url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{file_key}?type=image"
            
            async with self._client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                with open(file_path, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
            
            logger.info(f"Successfully downloaded image {file_key} from message {message_id} to {file_path}")
            return str(file_path.absolute())
            
        except Exception as e:
            logger.error(f"Failed to download image {file_key} from message {message_id} in Feishu: {e}")
            raise RuntimeError(f"图片下载失败: {e}")

    async def aclose(self):
        """
        优雅关闭内部的 httpx 异步连接池。
        """
        await self._client.aclose()
