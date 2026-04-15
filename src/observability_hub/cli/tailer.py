import json
import time
import sys
import threading
import os
from pathlib import Path

# ============================================================
# 全栈监控层 —— CLI 实时日志工具 (CLI Log Tailer)
#
# 本模块实现了规格 OB-P0-06（CLI 实时日志）。
# ============================================================


class CLILogTailer:
    """
    基于命令行的实时日志追踪工具 (OB-P0-06)。

    设计意图：
        提供类似 `tail -f` 的实时日志输出能力，从 JSONL 日志文件末尾开始
        持续读取新写入的行，并按 trace_id 进行过滤输出。

    Args:
        log_file (str): 要追踪的 JSONL 日志文件路径。
    """
    def __init__(self, log_file: str = "logs/debug_trace.jsonl"):
        self.log_file = Path(log_file)

    def tail(self, target_trace_id: str | None = None, stop_event: threading.Event | None = None) -> None:
        """
        实时追踪并输出日志，支持按 trace_id 过滤。
        """
        while True:
            if not self.log_file.exists():
                print(f"Waiting for log file {self.log_file} to be created...")
                while not self.log_file.exists():
                    if stop_event is not None and stop_event.is_set():
                        return
                    time.sleep(0.5)

            # 获取当前文件的 inode，用于判断是否发生了文件轮转
            try:
                current_ino = os.stat(self.log_file).st_ino
            except FileNotFoundError:
                continue

            with open(self.log_file, "r", encoding="utf-8") as f:
                f.seek(0, 2)  # 将指针移到文件末尾，跳过历史日志
                while stop_event is None or not stop_event.is_set():
                    line = f.readline()
                    if not line:
                        # 暂无新内容，检查是否发生了文件轮转
                        try:
                            if os.stat(self.log_file).st_ino != current_ino:
                                print("Log file rotated. Reopening new file...", file=sys.stderr)
                                break  # 跳出内层读取循环，重新打开新文件
                        except FileNotFoundError:
                            pass
                        
                        time.sleep(0.1)
                        continue

                    try:
                        record = json.loads(line)
                        if target_trace_id is None or record.get("trace_id") == target_trace_id:
                            self._print_record(record)
                    except json.JSONDecodeError as e:
                        print(f"WARNING: JSON decode error on line: {line.strip()} - {e}", file=sys.stderr)
                    except Exception as e:
                        print(f"CLI Logger internal error: {e}", file=sys.stderr)

            if stop_event is not None and stop_event.is_set():
                break

    def _print_record(self, record: dict) -> None:
        """格式化并打印单条日志记录到标准输出"""
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(record.get('timestamp_ms', 0) / 1000))
        level = record.get('level', 'INFO')
        trace_id = record.get('trace_id', 'unknown')
        payload = json.dumps(record.get('payload', {}), ensure_ascii=False, indent=2)
        print(f"[{timestamp}] [{level}] [TraceID: {trace_id}]\n{payload}\n{'-'*40}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Tail and filter debug logs by TraceID.")
    parser.add_argument("--trace-id", type=str, help="The TraceID to filter logs by.", default=None)
    parser.add_argument("--log-file", type=str, help="Path to the JSONL log file.", default="logs/debug_trace.jsonl")
    args = parser.parse_args()

    tailer = CLILogTailer(log_file=args.log_file)
    print(f"Tailing logs from {args.log_file} (TraceID Filter: {args.trace_id or 'ALL'})...")
    tailer.tail(target_trace_id=args.trace_id)
