import json
import time
from pathlib import Path

class CLILogTailer:
    """
    (OB-P0-06) CLI 实时日志工具。

    设计意图：
    提供基于命令行的日志输出工具，可以按 TraceID 实时过滤 JSONL 文件中写入的数据。
    """
    def __init__(self, log_file: str = "logs/debug_trace.jsonl"):
        self.log_file = Path(log_file)

    def tail(self, target_trace_id: str | None = None) -> None:
        """
        实时监听并输出日志，支持按 trace_id 过滤。
        可以通过在命令行中运行脚本调用此方法实现实时调试。
        """
        if not self.log_file.exists():
            print(f"Log file {self.log_file} does not exist yet.")
            return

        with open(self.log_file, "r", encoding="utf-8") as f:
            f.seek(0, 2)  # Go to the end of the file
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.1)
                    continue

                try:
                    record = json.loads(line)
                    if target_trace_id is None or record.get("trace_id") == target_trace_id:
                        self._print_record(record)
                except json.JSONDecodeError:
                    pass

    def _print_record(self, record: dict) -> None:
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
