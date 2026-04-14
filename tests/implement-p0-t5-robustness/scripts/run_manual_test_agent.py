#!/usr/bin/env python3
import asyncio
import multiprocessing as mp
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import shlex

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.app.bootstrap import build_application
from src.app.config import AppConfig, load_config
from src.channel_gateway.domain.events import UniversalEvent
from src.channel_gateway.domain.responses import ReplyText
from src.observability_hub.jsonl_storage import JSONLStorageEngine
from src.observability_hub.recording import LogLevel, generate_trace_id, record
from src.orchestration_engine.contracts import CapabilityDescription, CapabilityRequest, CapabilityResult


@dataclass(frozen=True)
class PendingApproval:
    ticket_id: str
    trace_id: str
    request: CapabilityRequest
    created_at_ms: int


def _now_ms() -> int:
    return int(time.time() * 1000)


def _extract_text(event: UniversalEvent) -> str:
    text = (event.text or "").strip()
    if text:
        return text
    return " ".join([c.data for c in event.contents if getattr(c, "type", None) == "text"]).strip()


def _format_result_for_text(result: CapabilityResult, *, max_chars: int = 3000) -> str:
    if result.success:
        if result.metadata.get("domain") == "model":
            provider = str(result.output.get("provider_id") or result.metadata.get("provider") or "unknown")
            model_name = str(result.output.get("model_name") or "")
            finish_reason = str(result.output.get("finish_reason") or "")
            content = str(result.output.get("content") or "")
            if not content:
                content = "(空回复)"
            text = "\n".join(
                [
                    f"provider={provider}",
                    f"model={model_name}",
                    f"finish_reason={finish_reason}",
                    "",
                    content,
                ]
            ).strip()
        else:
            text = str(result.output)
        if len(text) > max_chars:
            return text[:max_chars] + f"\n...(truncated, total={len(text)} chars)"
        return text
    return f"ERROR[{result.error_code}]: {result.error_message or ''} metadata={result.metadata}"


def _preview(value: Any, *, max_chars: int = 200) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"...(truncated,total={len(text)})"


def _parse_command(text: str) -> tuple[str, list[str]]:
    cleaned = text.strip()
    if cleaned.startswith("@agent"):
        cleaned = cleaned[len("@agent") :].strip()
    if not cleaned.startswith("/"):
        return "/echo", [cleaned]
    try:
        parts = shlex.split(cleaned)
    except Exception:
        parts = cleaned.split()
    if not parts:
        return "/help", []
    return parts[0], parts[1:]


def _build_help() -> str:
    return "\n".join(
        [
            "可用指令：",
            "- /help",
            "- /whoami",
            "- /echo <text>",
            "- /echo-long <n_chars>",
            "- /model <prompt>",
            "- /browser-probe",
            "- /shell <cmd> [--reuse-ticket <ticket_id>]",
            "- /fs-read <path> [--reuse-ticket <ticket_id>]",
            "- /approve <ticket_id>",
            "- /spam-log <n_records>",
            "- /delay <seconds> <tag>",
            "",
            "说明：",
            "- /shell 与 /fs-read 会触发安全原语（灰名单）并返回 ticket_id，需 /approve 后放行。",
            "- 每次回复都会包含 TraceID，配合 cli_logger 做过滤观测。",
        ]
    )


async def _send_reply(
    sender: Any,
    target_event: UniversalEvent,
    *,
    trace_id: str,
    text: str,
    on_result: Any | None = None,
) -> None:
    payload = f"[TraceID: {trace_id}]\n{text}"
    reply = ReplyText(content=payload)
    try:
        result = await sender.send_text_reply(reply, target_event)
    except Exception as exc:
        result = {"status": "exception", "error": str(exc)}
    if on_result is not None:
        try:
            on_result(result)
        except Exception:
            pass


def _register_test_tool_capabilities(*, hub: Any) -> None:
    async def _shell_exec(req: CapabilityRequest) -> CapabilityResult:
        from src.skill_hub.security import default_security_policy

        cmd = str(req.payload.get("command", "") or "")
        approved = req.payload.get("approved_ticket_id")
        stdout = default_security_policy.secure_shell.execute(cmd, approved_ticket_id=approved)
        return CapabilityResult(capability_id=req.capability_id, success=True, output={"stdout": stdout})

    async def _fs_read(req: CapabilityRequest) -> CapabilityResult:
        from src.skill_hub.security import default_security_policy

        path = str(req.payload.get("path", "") or "")
        approved = req.payload.get("approved_ticket_id")
        content = default_security_policy.secure_fs.read_text(path, approved_ticket_id=approved)
        return CapabilityResult(capability_id=req.capability_id, success=True, output={"content": content})

    shell_cap = CapabilityDescription(
        capability_id="tool.test.shell.exec",
        domain="tool",
        name="test_shell_exec",
        description="(T5 手动测试) 受安全原语保护的 shell 执行能力，用于验证 ticket 授权与核销。",
        input_schema={"type": "object", "properties": {"command": {"type": "string"}, "approved_ticket_id": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"stdout": {"type": "string"}}},
        metadata={"kind": "manual_test"},
    )
    fs_cap = CapabilityDescription(
        capability_id="tool.test.fs.read_text",
        domain="tool",
        name="test_fs_read_text",
        description="(T5 手动测试) 受安全原语保护的文件读取能力，用于验证路径边界与授权。",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}, "approved_ticket_id": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"content": {"type": "string"}}},
        metadata={"kind": "manual_test"},
    )
    hub.register_capability(shell_cap, _shell_exec)
    hub.register_capability(fs_cap, _fs_read)


async def run_manual_test_agent() -> None:
    print("=" * 72)
    print("P0 T5 手动测试 Agent 启动中（Feishu Long Connection -> CapabilityHub -> Reply + JSONL）")
    print("=" * 72)

    config = load_config()
    app = build_application(config)
    gateway = app.modules.channel_gateway
    sender = gateway.feishu_sender

    if app.config.feishu is None:
        print("错误：未找到飞书配置，请先运行：.venv/bin/python -m src.app.main config-feishu ...")
        return

    runtime = gateway.feishu_long_connection
    if not runtime.initialized:
        raise RuntimeError(runtime.error or "feishu_long_connection_unavailable")

    log_max_bytes = int(os.getenv("QF_DEBUG_LOG_MAX_BYTES", "8192"))
    log_backup_count = int(os.getenv("QF_DEBUG_LOG_BACKUP_COUNT", "5"))
    jsonl_engine = JSONLStorageEngine(log_dir="logs", max_bytes=log_max_bytes, backup_count=log_backup_count)
    print(f"[观测] JSONL 日志：logs/debug_trace.jsonl (max_bytes={log_max_bytes}, backups={log_backup_count})")

    capability_hub = app.modules.skill_hub.capability_hub
    _register_test_tool_capabilities(hub=capability_hub)

    pending: dict[str, PendingApproval] = {}

    process_context = mp.get_context("spawn")
    event_queue: mp.Queue = process_context.Queue()
    long_connection_process = process_context.Process(
        target=_run_long_connection_process,
        args=(app.config, event_queue),
        daemon=True,
    )

    active_tasks: set[asyncio.Task[None]] = set()

    def _write_log(tid: str, data: Any, level: LogLevel = LogLevel.INFO) -> None:
        jsonl_engine.write_record(record(trace_id=tid, data=data, level=level))

    async def _invoke(request: CapabilityRequest, *, tid: str, target_event: UniversalEvent) -> None:
        invoke_record: dict[str, Any] = {
            "type": "capability.invoke",
            "capability_id": request.capability_id,
            "payload_keys": list(request.payload.keys()),
        }
        if request.capability_id.startswith("model."):
            invoke_record["payload.prompt_preview"] = _preview(request.payload.get("prompt"))
            invoke_record["payload.model_tag"] = request.payload.get("model_tag")
            invoke_record["payload.model_name"] = request.payload.get("model_name")
            meta = request.payload.get("metadata")
            if isinstance(meta, dict):
                invoke_record["payload.metadata_keys"] = list(meta.keys())
        _write_log(tid, invoke_record)
        result = await capability_hub.invoke(request)
        _write_log(
            tid,
            {
                "type": "capability.result",
                "capability_id": request.capability_id,
                "success": result.success,
                "error_code": result.error_code,
                "metadata": result.metadata,
                "output.provider_id": result.output.get("provider_id"),
                "output.finish_reason": result.output.get("finish_reason"),
                "output.content_len": len(str(result.output.get("content") or "")),
                "output.content_preview": _preview(result.output.get("content")),
            },
            level=LogLevel.INFO if result.success else LogLevel.WARNING,
        )

        if (not result.success) and result.error_code == "requires_user_approval":
            ticket_id = str(result.metadata.get("ticket_id") or "")
            if ticket_id:
                pending[ticket_id] = PendingApproval(
                    ticket_id=ticket_id,
                    trace_id=tid,
                    request=request,
                    created_at_ms=_now_ms(),
                )
            await _send_reply(
                sender,
                target_event,
                trace_id=tid,
                text="\n".join(
                    [
                        "操作需要人工授权（安全原语灰名单）。",
                        f"ticket_id = {ticket_id}",
                        "执行：/approve <ticket_id> 进行授权后自动重试。",
                    ]
                ),
            on_result=lambda r: _write_log(
                tid,
                {
                    "type": "feishu.send",
                    "status": r.get("status"),
                    "error": r.get("error"),
                    "chunk_index": r.get("chunk_index"),
                    "response_keys": list(r.keys()) if isinstance(r, dict) else None,
                    "data_keys": list((r.get("data") or {}).keys()) if isinstance(r, dict) and isinstance(r.get("data"), dict) else None,
                },
            ),
            )
            return

        await _send_reply(
            sender,
            target_event,
            trace_id=tid,
            text=_format_result_for_text(result),
            on_result=lambda r: _write_log(
                tid,
                {
                    "type": "feishu.send",
                    "status": r.get("status"),
                    "error": r.get("error"),
                    "chunk_index": r.get("chunk_index"),
                    "response_keys": list(r.keys()) if isinstance(r, dict) else None,
                    "data_keys": list((r.get("data") or {}).keys()) if isinstance(r, dict) and isinstance(r.get("data"), dict) else None,
                },
            ),
        )

    async def _handle_event(event: UniversalEvent) -> None:
        tid = generate_trace_id()
        text = _extract_text(event)
        cmd, args = _parse_command(text)

        _write_log(
            tid,
            {
                "type": "event.received",
                "platform": event.platform_type,
                "user_id": event.user_id,
                "group_id": event.group_id,
                "message_id": event.message_id,
                "logical_uid": event.logical_uid,
                "text": text,
                "cmd": cmd,
                "args": args,
            },
        )

        if cmd in ("/help",):
            await _send_reply(
                sender,
                event,
                trace_id=tid,
                text=_build_help(),
                on_result=lambda r: _write_log(tid, {"type": "feishu.send", "status": r.get("status"), "error": r.get("error")}),
            )
            return

        if cmd in ("/whoami",):
            await _send_reply(
                sender,
                event,
                trace_id=tid,
                text=f"user_id={event.user_id}\ngroup_id={event.group_id}\nlogical_uid={event.logical_uid}",
                on_result=lambda r: _write_log(tid, {"type": "feishu.send", "status": r.get("status"), "error": r.get("error")}),
            )
            return

        if cmd in ("/echo",):
            await _send_reply(
                sender,
                event,
                trace_id=tid,
                text=" ".join(args).strip(),
                on_result=lambda r: _write_log(tid, {"type": "feishu.send", "status": r.get("status"), "error": r.get("error")}),
            )
            return

        if cmd in ("/echo-long",):
            n = int(args[0]) if args else 9000
            await _send_reply(
                sender,
                event,
                trace_id=tid,
                text=("L" * n),
                on_result=lambda r: _write_log(tid, {"type": "feishu.send", "status": r.get("status"), "error": r.get("error"), "chunk_index": r.get("chunk_index")}),
            )
            return

        if cmd in ("/delay",):
            seconds = float(args[0]) if len(args) >= 1 else 3.0
            tag = args[1] if len(args) >= 2 else ""
            await _send_reply(
                sender,
                event,
                trace_id=tid,
                text=f"处理中：delay={seconds}s tag={tag}",
                on_result=lambda r: _write_log(tid, {"type": "feishu.send", "status": r.get("status"), "error": r.get("error")}),
            )
            await asyncio.sleep(seconds)
            await _send_reply(
                sender,
                event,
                trace_id=tid,
                text=f"完成：delay={seconds}s tag={tag}",
                on_result=lambda r: _write_log(tid, {"type": "feishu.send", "status": r.get("status"), "error": r.get("error")}),
            )
            return

        if cmd in ("/spam-log",):
            n = int(args[0]) if args else 200
            for i in range(n):
                _write_log(tid, {"type": "spam", "i": i, "payload": "X" * 80})
            await _send_reply(
                sender,
                event,
                trace_id=tid,
                text=f"已写入 {n} 条 JSONL 记录（用于轮转测试）。",
                on_result=lambda r: _write_log(tid, {"type": "feishu.send", "status": r.get("status"), "error": r.get("error")}),
            )
            return

        if cmd in ("/approve",):
            if not args:
                await _send_reply(
                    sender,
                    event,
                    trace_id=tid,
                    text="用法：/approve <ticket_id>",
                    on_result=lambda r: _write_log(tid, {"type": "feishu.send", "status": r.get("status"), "error": r.get("error")}),
                )
                return
            ticket_id = args[0].strip()
            pending_req = pending.get(ticket_id)
            if pending_req is None:
                await _send_reply(
                    sender,
                    event,
                    trace_id=tid,
                    text=f"未找到待授权的 ticket_id：{ticket_id}",
                    on_result=lambda r: _write_log(tid, {"type": "feishu.send", "status": r.get("status"), "error": r.get("error")}),
                )
                return
            approved_payload = dict(pending_req.request.payload)
            approved_payload["approved_ticket_id"] = ticket_id
            req = CapabilityRequest(
                capability_id=pending_req.request.capability_id,
                payload=approved_payload,
                metadata=dict(pending_req.request.metadata),
            )
            await _send_reply(
                sender,
                event,
                trace_id=tid,
                text=f"已授权 ticket_id={ticket_id}，正在重试…",
                on_result=lambda r: _write_log(tid, {"type": "feishu.send", "status": r.get("status"), "error": r.get("error")}),
            )
            del pending[ticket_id]
            await _invoke(req, tid=tid, target_event=event)
            return

        if cmd in ("/browser-probe",):
            req = CapabilityRequest(
                capability_id="tool.browser.open",
                payload={"url": "https://example.com", "probe_only": True},
                metadata={},
            )
            await _invoke(req, tid=tid, target_event=event)
            return

        if cmd in ("/model",):
            prompt = " ".join(args).strip()
            if not prompt:
                await _send_reply(
                    sender,
                    event,
                    trace_id=tid,
                    text="用法：/model <prompt>",
                    on_result=lambda r: _write_log(tid, {"type": "feishu.send", "status": r.get("status"), "error": r.get("error")}),
                )
                return
            if not (os.getenv("QF_MINIMAX_API_KEY") or os.getenv("MINIMAX_API_KEY")):
                await _send_reply(
                    sender,
                    event,
                    trace_id=tid,
                    text="模型未配置（缺少 QF_MINIMAX_API_KEY 或 MINIMAX_API_KEY），已降级为 echo：\n" + prompt,
                    on_result=lambda r: _write_log(tid, {"type": "feishu.send", "status": r.get("status"), "error": r.get("error")}),
                )
                return
            req = CapabilityRequest(
                capability_id="model.chat.default",
                payload={
                    "prompt": prompt,
                    "model_tag": "minimax",
                    "metadata": {"provider": "minimax"},
                },
                metadata={},
            )
            await _invoke(req, tid=tid, target_event=event)
            return

        if cmd in ("/shell",):
            if not args:
                await _send_reply(
                    sender,
                    event,
                    trace_id=tid,
                    text="用法：/shell <cmd> [--reuse-ticket <ticket_id>]",
                    on_result=lambda r: _write_log(tid, {"type": "feishu.send", "status": r.get("status"), "error": r.get("error")}),
                )
                return
            reuse_ticket = None
            if "--reuse-ticket" in args:
                idx = args.index("--reuse-ticket")
                if idx + 1 < len(args):
                    reuse_ticket = args[idx + 1]
                    args = args[:idx] + args[idx + 2 :]
            command = " ".join(args).strip()
            payload = {"command": command}
            if reuse_ticket:
                payload["approved_ticket_id"] = reuse_ticket
            req = CapabilityRequest(
                capability_id="tool.test.shell.exec",
                payload=payload,
                metadata={},
            )
            await _invoke(req, tid=tid, target_event=event)
            return

        if cmd in ("/fs-read",):
            if not args:
                await _send_reply(
                    sender,
                    event,
                    trace_id=tid,
                    text="用法：/fs-read <path> [--reuse-ticket <ticket_id>]",
                    on_result=lambda r: _write_log(tid, {"type": "feishu.send", "status": r.get("status"), "error": r.get("error")}),
                )
                return
            reuse_ticket = None
            if "--reuse-ticket" in args:
                idx = args.index("--reuse-ticket")
                if idx + 1 < len(args):
                    reuse_ticket = args[idx + 1]
                    args = args[:idx] + args[idx + 2 :]
            path = " ".join(args).strip()
            payload = {"path": path}
            if reuse_ticket:
                payload["approved_ticket_id"] = reuse_ticket
            req = CapabilityRequest(
                capability_id="tool.test.fs.read_text",
                payload=payload,
                metadata={},
            )
            result = await capability_hub.invoke(req)
            if (not result.success) and result.error_code == "requires_user_approval":
                ticket_id = str(result.metadata.get("ticket_id") or "")
                if ticket_id:
                    pending[ticket_id] = PendingApproval(ticket_id=ticket_id, trace_id=tid, request=req, created_at_ms=_now_ms())
                await _send_reply(
                    sender,
                    event,
                    trace_id=tid,
                    text=f"读取需要授权。ticket_id={ticket_id}\n执行：/approve <ticket_id> 进行授权后重试。",
                    on_result=lambda r: _write_log(tid, {"type": "feishu.send", "status": r.get("status"), "error": r.get("error")}),
                )
                return
            if result.success:
                content = str(result.output.get("content", ""))
                max_chars = 2000
                if len(content) > max_chars:
                    content = content[:max_chars] + f"\n...(truncated, total={len(content)} chars)"
                await _send_reply(sender, event, trace_id=tid, text=content)
                return
            await _send_reply(
                sender,
                event,
                trace_id=tid,
                text=_format_result_for_text(result),
                on_result=lambda r: _write_log(tid, {"type": "feishu.send", "status": r.get("status"), "error": r.get("error")}),
            )
            return

        await _send_reply(
            sender,
            event,
            trace_id=tid,
            text=f"未知指令：{cmd}\n\n" + _build_help(),
            on_result=lambda r: _write_log(tid, {"type": "feishu.send", "status": r.get("status"), "error": r.get("error")}),
        )

    async def _consume_event_loop() -> None:
        while True:
            event = await asyncio.to_thread(event_queue.get)
            task = asyncio.create_task(_handle_event(event))
            active_tasks.add(task)
            task.add_done_callback(active_tasks.discard)

    async def _run_long_connection() -> None:
        long_connection_process.start()
        try:
            while long_connection_process.is_alive():
                await asyncio.sleep(1)
        finally:
            if long_connection_process.is_alive():
                long_connection_process.terminate()
                long_connection_process.join(timeout=3)

    print("服务启动完成：请在飞书（私聊/群聊）向机器人发送 /help 开始手动验收。")
    try:
        await asyncio.gather(_consume_event_loop(), _run_long_connection())
    finally:
        try:
            await sender.aclose()
        except Exception:
            pass


def _run_long_connection_process(config: AppConfig, event_queue: mp.Queue) -> None:
    app = build_application(config)
    gateway = app.modules.channel_gateway
    runtime = gateway.feishu_long_connection
    if not runtime.initialized:
        raise RuntimeError(runtime.error or "feishu_long_connection_unavailable")

    def _on_text_event(event: UniversalEvent) -> None:
        event_queue.put(event)

    gateway.run_feishu_long_connection(app.config.feishu, _on_text_event)


if __name__ == "__main__":
    try:
        asyncio.run(run_manual_test_agent())
    except KeyboardInterrupt:
        print("\n手动测试结束。")
