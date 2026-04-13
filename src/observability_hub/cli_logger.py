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
#
# 核心功能：
#   像 Linux 的 `tail -f` 命令一样，实时追踪 JSONL 日志文件的新增内容，
#   并支持按 trace_id 过滤，让开发者可以只看某一次具体请求的完整链路日志。
#
# 典型使用场景：
#   1. 本地调试时，在另一个终端运行：
#      python -m src.observability_hub.cli_logger --trace-id <trace_id>
#   2. 实时观察 Agent 的每一步决策、工具调用和模型输出。
#
# ============================================================


class CLILogTailer:
    """
    基于命令行的实时日志追踪工具 (OB-P0-06)。

    设计意图：
        提供类似 `tail -f` 的实时日志输出能力，从 JSONL 日志文件末尾开始
        持续读取新写入的行，并按 trace_id 进行过滤输出。
        开发者可以在调试时通过命令行直接运行本工具，精准定位某次请求的全链路日志。

    Args:
        log_file (str): 要追踪的 JSONL 日志文件路径。默认为 "logs/debug_trace.jsonl"，
                        与 JSONLStorageEngine 的默认写入路径保持一致。
    """
    def __init__(self, log_file: str = "logs/debug_trace.jsonl"):
        # 将字符串路径转为 Path 对象，便于后续做存在性检查和文件操作
        self.log_file = Path(log_file)

    def tail(self, target_trace_id: str | None = None, stop_event: threading.Event | None = None) -> None:
        """
        实时追踪并输出日志，支持按 trace_id 过滤。

        执行流程：
            1. 检查日志文件是否存在，不存在则等待其创建。
            2. 打开文件并将读取指针移到末尾（只看后续新增内容，不回放历史）。
            3. 循环读取新行：
               - 有新行 → 解析 JSON → 按 trace_id 过滤 → 打印
               - 无新行 → sleep 0.1 秒后继续轮询
               - 接收到 stop_event 信号时退出循环。

        Args:
            target_trace_id (str | None): 要过滤的 TraceID。
                为 None 时输出所有日志；指定时只输出匹配该 TraceID 的记录。
            stop_event (threading.Event | None): 外部传入的停止信号。
                如果提供了该事件对象，当其被 set() 时，循环安全退出。
        """
        while True:
            if not self.log_file.exists():
                print(f"Waiting for log file {self.log_file} to be created...")
                while not self.log_file.exists():
                    if stop_event is not None and stop_event.is_set():
                        return
                    time.sleep(0.5)

            # 获取当前文件的 inode，用于判断是否发生了文件轮转
            current_ino = os.stat(self.log_file).st_ino

            with open(self.log_file, "r", encoding="utf-8") as f:
                f.seek(0, 2)  # 将指针移到文件末尾（seek 末尾偏移 0），跳过历史日志
                # [修复 REV-OB06-BUG-001]
                # 引入了外部干预标识 stop_event。
                # 直接终结了此前此函数一旦调用就永不退出的僵尸级 while True 死循环，允许外层优雅收回线程。
                while stop_event is None or not stop_event.is_set():
                    line = f.readline()
                    if not line:
                        # 暂无新内容，检查是否发生了文件轮转
                        try:
                            if os.stat(self.log_file).st_ino != current_ino:
                                print("Log file rotated. Reopening new file...", file=sys.stderr)
                                break  # 跳出内层读取循环，重新打开新文件
                        except FileNotFoundError:
                            # 文件可能在轮转瞬间被移走，短暂不存在
                            pass
                        
                        # 等待 0.1 秒后继续轮询（避免 CPU 空转）
                        time.sleep(0.1)
                        continue

                    try:
                        record = json.loads(line)
                        # 过滤逻辑：target_trace_id 为 None 时全部输出，否则仅匹配指定 TraceID
                        if target_trace_id is None or record.get("trace_id") == target_trace_id:
                            self._print_record(record)
                    except json.JSONDecodeError as e:
                        # [修复 REV-OB06-CON-001]
                        # 将损坏报错写入系统标准错误 (stderr)。
                        # 这彻底打碎了“遇到读不出的残缺日志行就直接 pass 当作无事发生”的静默丢弃潜规则，
                        # 避免并发错乱导致的问题被无形掩盖。
                        print(f"WARNING: JSON decode error on line: {line.strip()} - {e}", file=sys.stderr)
                    except Exception as e:
                        # 即使发生格式化或输出错误，也不能让后台追踪线程崩溃退出
                        print(f"CLI Logger internal error: {e}", file=sys.stderr)

            # 如果外层收到了退出信号，彻底退出大循环
            if stop_event is not None and stop_event.is_set():
                break

    def _print_record(self, record: dict) -> None:
        """
        格式化并打印单条日志记录到标准输出。

        输出格式：
            [YYYY-MM-DD HH:MM:SS] [LEVEL] [TraceID: xxx]
            { payload JSON }
            ----------------------------------------

        Args:
            record (dict): 从 JSONL 文件解析出的单条日志字典，
                           字段对应 JSONLStorageEngine.write_record 写入的结构。
        """
        # 将毫秒级时间戳转换为人类可读的本地时间字符串
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(record.get('timestamp_ms', 0) / 1000))
        level = record.get('level', 'INFO')          # 日志级别，默认 INFO
        trace_id = record.get('trace_id', 'unknown') # TraceID，用于关联请求链路
        # payload 格式化为带缩进的 JSON，ensure_ascii=False 保证中文正常显示
        payload = json.dumps(record.get('payload', {}), ensure_ascii=False, indent=2)
        print(f"[{timestamp}] [{level}] [TraceID: {trace_id}]\n{payload}\n{'-'*40}")


# ============================================================
# CLI 入口 —— 直接运行本脚本时的参数解析
#
# 使用方式：
#   python -m src.observability_hub.cli_logger \
#       --log-file logs/debug_trace.jsonl \
#       --trace-id <your_trace_id>
# ============================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Tail and filter debug logs by TraceID.")
    # --trace-id: 指定要过滤的 TraceID，不传则输出所有日志
    parser.add_argument("--trace-id", type=str, help="The TraceID to filter logs by.", default=None)
    # --log-file: 指定要追踪的 JSONL 文件路径
    parser.add_argument("--log-file", type=str, help="Path to the JSONL log file.", default="logs/debug_trace.jsonl")
    args = parser.parse_args()

    tailer = CLILogTailer(log_file=args.log_file)
    print(f"Tailing logs from {args.log_file} (TraceID Filter: {args.trace_id or 'ALL'})...")
    tailer.tail(target_trace_id=args.trace_id)

