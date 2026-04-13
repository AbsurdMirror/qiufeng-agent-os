import io
import json
import os
import threading
import time
from contextlib import redirect_stderr, redirect_stdout

from src.observability_hub.cli_logger import CLILogTailer
from src.observability_hub.jsonl_storage import JSONLStorageEngine
from src.observability_hub.recording import LogLevel, NormalizedRecord


def test_ob_t5_01_jsonl_write_record_appends_a_line(tmp_path):
    """测试项 OB-T5-01: write_record 追加写入"""
    engine = JSONLStorageEngine(log_dir=str(tmp_path), max_bytes=1024 * 1024, backup_count=2)
    engine.write_record(
        NormalizedRecord(
            trace_id="trace_1",
            level=LogLevel.INFO,
            payload={"k": "v"},
            payload_type="dict",
            timestamp_ms=123,
        )
    )

    lines = (tmp_path / "debug_trace.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["trace_id"] == "trace_1"
    assert parsed["payload"]["k"] == "v"


def test_ob_t5_02_jsonl_rotation_creates_backups(tmp_path):
    """测试项 OB-T5-02: 文件轮转"""
    engine = JSONLStorageEngine(log_dir=str(tmp_path), max_bytes=200, backup_count=2)
    for i in range(50):
        engine.write_record(
            NormalizedRecord(
                trace_id=f"trace_{i}",
                level=LogLevel.INFO,
                payload={"msg": "X" * 50, "i": i},
                payload_type="dict",
                timestamp_ms=1000 + i,
            )
        )

    assert (tmp_path / "debug_trace.jsonl").exists()
    assert (tmp_path / "debug_trace.jsonl.1").exists()


def test_ob_t5_03_cli_log_tailer_filters_by_trace_id(tmp_path):
    """测试项 OB-T5-03: CLILogTailer TraceID 过滤"""
    log_file = tmp_path / "debug_trace.jsonl"
    log_file.write_text("", encoding="utf-8")

    stop_event = threading.Event()
    tailer = CLILogTailer(log_file=str(log_file))

    out = io.StringIO()
    err = io.StringIO()

    def _run():
        tailer.tail(target_trace_id="trace_target", stop_event=stop_event)

    with redirect_stdout(out), redirect_stderr(err):
        t = threading.Thread(target=_run, daemon=True)
        t.start()

        time.sleep(0.2)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {"trace_id": "trace_other", "level": "INFO", "payload": {"a": 1}, "timestamp_ms": 1},
                    ensure_ascii=False,
                )
                + "\n"
            )
            f.flush()
            os.fsync(f.fileno())
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {"trace_id": "trace_target", "level": "INFO", "payload": {"b": 2}, "timestamp_ms": 2},
                    ensure_ascii=False,
                )
                + "\n"
            )
            f.flush()
            os.fsync(f.fileno())

        time.sleep(0.4)
        stop_event.set()
        t.join(timeout=2)

    output = out.getvalue()
    assert "TraceID: trace_target" in output
    assert "TraceID: trace_other" not in output


def test_ob_t5_04_cli_log_tailer_stop_event_exits(tmp_path):
    """测试项 OB-T5-04: stop_event 可退出"""
    log_file = tmp_path / "debug_trace.jsonl"
    log_file.write_text("", encoding="utf-8")

    stop_event = threading.Event()
    tailer = CLILogTailer(log_file=str(log_file))

    t = threading.Thread(target=lambda: tailer.tail(stop_event=stop_event), daemon=True)
    t.start()
    time.sleep(0.1)
    stop_event.set()
    t.join(timeout=2)

    assert t.is_alive() is False
