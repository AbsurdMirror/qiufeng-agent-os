from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from typing import Any, Callable, Mapping

from src.app.bootstrap import Application


def run_webhook_server(app: Application) -> None:
    """
    启动飞书 Webhook 模式的 HTTP 服务器。
    
    使用 Python 内置的 HTTPServer 模块，无需额外安装 FastAPI/Uvicorn。
    主要用于接收飞书推送的事件（如 URL 挑战校验、文本消息），并打印/记录。
    
    Args:
        app: 全局应用上下文对象。
    """
    gateway = app.modules.channel_gateway
    observability = app.modules.observability_hub
    parse_entry = gateway.feishu_webhook_entry
    trace_id_generator = observability.trace_id_generator
    recorder = observability.record

    class WebhookHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            """处理飞书发来的 POST 推送请求"""
            # 1. 路由拦截：只处理 /feishu/webhook 路径
            if self.path != "/feishu/webhook":
                self._send_json(404, {"ok": False, "error": "not_found"})
                return

            # 2. 读取并解析请求体 JSON
            raw_payload = self._read_json()
            if raw_payload is None:
                self._send_json(400, {"ok": False, "error": "invalid_json"})
                return

            # 3. 分配 TraceID
            trace_id = trace_id_generator()
            
            # 4. 交由网关层进行飞书事件解析
            try:
                result = _handle_feishu_webhook(
                    parse_entry=parse_entry,
                    recorder=recorder,
                    trace_id=trace_id,
                    payload=raw_payload,
                )
            except ValueError as error:
                # 解析失败（如缺少必要字段），返回 400
                self._send_json(400, {"ok": False, "error": str(error), "trace_id": trace_id})
                return

            # 解析成功，返回 200 (或者 challenge 字段)
            self._send_json(200, result)

        def log_message(self, fmt: str, *args: Any) -> None:
            # 禁用默认的终端访问日志打印，保持终端清爽，依赖 recorder 打点
            return

        def _read_json(self) -> dict[str, Any] | None:
            """安全地从请求流中读取并反序列化 JSON"""
            content_length = self.headers.get("Content-Length")
            if content_length is None:
                return None
            try:
                size = int(content_length)
            except ValueError:
                return None
            raw = self.rfile.read(size)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return None
            if not isinstance(payload, dict):
                return None
            return payload

        def _send_json(self, status_code: int, body: Mapping[str, Any]) -> None:
            """统一的 JSON 响应发送方法"""
            output = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(output)))
            self.end_headers()
            self.wfile.write(output)

    server = HTTPServer((app.config.host, app.config.port), WebhookHandler)
    print(
        f"{app.config.app_name} webhook server listening at "
        f"http://{app.config.host}:{app.config.port}/feishu/webhook"
    )
    if app.config.feishu is None:
        print(f"feishu settings not configured, run: python -m src.app.main config-feishu")
    else:
        print(f"feishu app_id loaded: {app.config.feishu.app_id}")
    server.serve_forever()


def _handle_feishu_webhook(
    parse_entry: Callable[[dict[str, Any]], Any],
    recorder: Callable[[str, Mapping[str, Any] | str | Any, Any], Any],
    trace_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    处理飞书的底层 JSON 载荷，区分是 Challenge 挑战请求还是正常事件请求。
    """
    result = parse_entry(payload)
    
    # 分支 1：处理飞书开放平台配置 Webhook 地址时的验证挑战 (url_verification)
    if result.is_challenge:
        recorder(trace_id=trace_id, data={"event_type": "challenge"}, level="INFO")
        print(json.dumps({"trace_id": trace_id, "challenge": result.challenge}, ensure_ascii=False))
        return {"challenge": result.challenge}

    # 分支 2：处理正常的文本消息事件
    if result.event is None:
        raise ValueError("invalid_event")
        
    event = result.event
    recorder(
        trace_id=trace_id,
        data={
            "event_type": "feishu_text",
            "event_id": event.event_id,
            "message_id": event.message_id,
            "user_id": event.user_id,
            "text": event.text,
        },
        level="INFO",
    )
    print(
        json.dumps(
            {
                "trace_id": trace_id,
                "platform": event.platform_type,
                "event_id": event.event_id,
                "user_id": event.user_id,
                "text": event.text,
            },
            ensure_ascii=False,
        )
    )
    return {"ok": True, "accepted": True, "trace_id": trace_id}
