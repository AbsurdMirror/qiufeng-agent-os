import json
from urllib import request


def request_tenant_access_token(app_id: str, app_secret: str, timeout_seconds: int = 8) -> tuple[bool, str]:
    """
    向飞书开放平台请求企业自建应用的 tenant_access_token。
    
    此函数主要用于：
    1. 在配置飞书参数时（config-feishu），通过获取 token 的结果来校验开发者输入的 
       app_id 和 app_secret 是否正确有效。
    2. 获取到的 token 可用于后续调用飞书其他 OpenAPI（发送消息、拉取用户信息等）。
    
    采用标准库 urllib 实现，避免引入额外的 HTTP 客户端依赖（如 requests 或 aiohttp）。
    
    Args:
        app_id: 飞书应用 ID
        app_secret: 飞书应用凭证
        timeout_seconds: HTTP 请求超时时间（秒）
        
    Returns:
        tuple[bool, str]: 
            - bool: 是否成功获取到 token (True 表示凭证有效)
            - str: 成功时返回 "ok"，失败时返回飞书接口的错误信息或网络异常信息
    """
    endpoint = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8")
    req = request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            response_payload = json.loads(resp.read().decode("utf-8"))
    except Exception as error:
        # 捕获网络异常（如超时、DNS 解析失败等）以及 HTTP 错误（如 400, 500）
        return False, str(error)

    code = response_payload.get("code")
    # 飞书 API 规范：code == 0 表示成功
    if code == 0 and isinstance(response_payload.get("tenant_access_token"), str):
        return True, "ok"
    
    msg = response_payload.get("msg")
    if isinstance(msg, str) and msg:
        return False, msg
    return False, "token_request_failed"

