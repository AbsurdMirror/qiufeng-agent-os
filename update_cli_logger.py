with open("src/observability_hub/cli_logger.py", "r") as f:
    content = f.read()

# Add stop_event support and warning for JSONDecodeError
import_text = """import json
import time
from pathlib import Path"""

replace_import_text = """import json
import time
import sys
import threading
from pathlib import Path"""

content = content.replace(import_text, replace_import_text)

search_tail_code = """
    def tail(self, target_trace_id: str | None = None) -> None:
        \"\"\"
        实时追踪并输出日志，支持按 trace_id 过滤（阻塞式，需 Ctrl+C 退出）。

        执行流程：
            1. 检查日志文件是否存在，不存在则直接返回。
            2. 打开文件并将读取指针移到末尾（只看后续新增内容，不回放历史）。
            3. 无限循环读取新行：
               - 有新行 → 解析 JSON → 按 trace_id 过滤 → 打印
               - 无新行 → sleep 0.1 秒后继续轮询

        Args:
            target_trace_id (str | None): 要过滤的 TraceID。
                为 None 时输出所有日志；指定时只输出匹配该 TraceID 的记录。

        风险：
            本方法是一个**永久阻塞循环**（while True），没有外部停止信号或超时机制，
            仅可通过 KeyboardInterrupt（Ctrl+C）退出。不可在服务程序或测试代码中调用。
            详见审阅报告 [REV-OB06-BUG-001]。
        \"\"\"
        if not self.log_file.exists():
            # 日志文件尚未创建（可能系统还未产生任何日志），直接退出
            print(f"Log file {self.log_file} does not exist yet.")
            return

        with open(self.log_file, "r", encoding="utf-8") as f:
            f.seek(0, 2)  # 将指针移到文件末尾（seek 末尾偏移 0），跳过历史日志
            while True:
                line = f.readline()
                if not line:
                    # 暂无新内容，等待 0.1 秒后继续轮询（避免 CPU 空转）
                    time.sleep(0.1)
                    continue

                try:
                    record = json.loads(line)
                    # 过滤逻辑：target_trace_id 为 None 时全部输出，否则仅匹配指定 TraceID
                    if target_trace_id is None or record.get("trace_id") == target_trace_id:
                        self._print_record(record)
                except json.JSONDecodeError:
                    # 静默跳过解析失败的行（可能是写入中途被截断的不完整行）
                    # 注意：此处 pass 会导致损坏行无感知丢失，见审阅报告 [REV-OB06-CON-001]
                    pass
"""

replace_tail_code = """
    def tail(self, target_trace_id: str | None = None, stop_event: threading.Event | None = None) -> None:
        \"\"\"
        实时追踪并输出日志，支持按 trace_id 过滤。

        执行流程：
            1. 检查日志文件是否存在，不存在则直接返回。
            2. 打开文件并将读取指针移到末尾（只看后续新增内容，不回放历史）。
            3. 循环读取新行（可通过 stop_event 中断）：
               - 有新行 → 解析 JSON → 按 trace_id 过滤 → 打印
               - 无新行 → sleep 0.1 秒后继续轮询

        Args:
            target_trace_id (str | None): 要过滤的 TraceID。
                为 None 时输出所有日志；指定时只输出匹配该 TraceID 的记录。
            stop_event (threading.Event | None): 外部传入的停止信号。当该信号被设置时，
                tail 方法会优雅退出。如果不传，则默认为无限循环。
        \"\"\"
        if not self.log_file.exists():
            # 日志文件尚未创建（可能系统还未产生任何日志），直接退出
            print(f"Log file {self.log_file} does not exist yet.")
            return

        with open(self.log_file, "r", encoding="utf-8") as f:
            f.seek(0, 2)  # 将指针移到文件末尾（seek 末尾偏移 0），跳过历史日志
            while not (stop_event and stop_event.is_set()):
                line = f.readline()
                if not line:
                    # 暂无新内容，等待 0.1 秒后继续轮询（避免 CPU 空转）
                    time.sleep(0.1)
                    continue

                try:
                    record = json.loads(line)
                    # 过滤逻辑：target_trace_id 为 None 时全部输出，否则仅匹配指定 TraceID
                    if target_trace_id is None or record.get("trace_id") == target_trace_id:
                        self._print_record(record)
                except json.JSONDecodeError as e:
                    # 输出警告日志，让开发者知道部分日志已损坏被跳过
                    print(f"[WARNING] Skipping corrupted log line: {line.strip()} - Error: {e}", file=sys.stderr)
"""

content = content.replace(search_tail_code, replace_tail_code)

with open("src/observability_hub/cli_logger.py", "w") as f:
    f.write(content)
