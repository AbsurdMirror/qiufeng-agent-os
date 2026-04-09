with open("src/observability_hub/jsonl_storage.py", "r") as f:
    content = f.read()

import_text = """import logging
import os
import time"""

replace_import_text = """import logging
import os
import time
import threading"""

content = content.replace(import_text, replace_import_text)

init_text = """        self.max_bytes = max_bytes       # 单文件大小上限（字节），超出触发轮转
        self.backup_count = backup_count # 保留历史备份文件的最大数量"""

replace_init_text = """        self.max_bytes = max_bytes       # 单文件大小上限（字节），超出触发轮转
        self.backup_count = backup_count # 保留历史备份文件的最大数量
        self._lock = threading.Lock()    # 文件轮转并发控制锁"""

content = content.replace(init_text, replace_init_text)

write_text = """        # 写入前先检查是否需要轮转（如果文件已超过 max_bytes，先轮转再写）
        self._rotate_if_needed()
        try:
            # 以追加模式（"a"）打开文件，每次调用只添加一行，不覆盖已有内容
            with open(self.log_file, "a", encoding="utf-8") as f:"""

replace_write_text = """        try:
            # 写入前先检查是否需要轮转（如果文件已超过 max_bytes，先轮转再写）
            self._rotate_if_needed()
            # 以追加模式（"a"）打开文件，每次调用只添加一行，不覆盖已有内容
            with open(self.log_file, "a", encoding="utf-8") as f:"""

content = content.replace(write_text, replace_write_text)


rotate_text = """    def _rotate_if_needed(self) -> None:
        \"\"\"
        检查主日志文件是否超过大小上限，超出则执行文件轮转（Rolling Rotation）。

        轮转逻辑（从最老到最新逐级重命名，倒序操作避免覆盖）：
            debug_trace.jsonl.4 → debug_trace.jsonl.5  (备份数量内最老的)
            debug_trace.jsonl.3 → debug_trace.jsonl.4
            ...
            debug_trace.jsonl.1 → debug_trace.jsonl.2
            debug_trace.jsonl   → debug_trace.jsonl.1  (当前主文件归档)
            （轮转完成后，主文件不存在，下次 write_record 会自动创建新文件）

        风险：本方法在多线程并发调用时存在 TOCTOU 竞态条件。
              详见审阅报告 [REV-OB0405-BUG-001]。
        \"\"\"
        # 主文件不存在时无需轮转（首次运行或刚刚完成上一次轮转后）
        if not self.log_file.exists():
            return
        # 文件大小未超过上限，无需轮转
        if self.log_file.stat().st_size < self.max_bytes:
            return

        # 执行文件轮转（倒序重命名，从最大序号往小遍历，避免先改小号导致大号被覆盖）
        # 例如：backup_count=5，range(4, 0, -1) = [4, 3, 2, 1]
        for i in range(self.backup_count - 1, 0, -1):
            src = self.log_dir / f"debug_trace.jsonl.{i}"
            dst = self.log_dir / f"debug_trace.jsonl.{i + 1}"
            if src.exists():
                # os.replace 是原子操作，等价于 mv，避免 rename 时中途崩溃留下残缺文件
                os.replace(src, dst)
        # 将当前主文件重命名为 .1，完成归档（旧的 .1 已在上面的循环中移到 .2）
        os.replace(self.log_file, self.log_dir / "debug_trace.jsonl.1")
        # 轮转完成后主文件 debug_trace.jsonl 不存在，下次 write_record 会自动创建"""

replace_rotate_text = """    def _rotate_if_needed(self) -> None:
        \"\"\"
        检查主日志文件是否超过大小上限，超出则执行文件轮转（Rolling Rotation）。

        轮转逻辑（从最老到最新逐级重命名，倒序操作避免覆盖）：
            debug_trace.jsonl.4 → debug_trace.jsonl.5  (备份数量内最老的)
            debug_trace.jsonl.3 → debug_trace.jsonl.4
            ...
            debug_trace.jsonl.1 → debug_trace.jsonl.2
            debug_trace.jsonl   → debug_trace.jsonl.1  (当前主文件归档)
            （轮转完成后，主文件不存在，下次 write_record 会自动创建新文件）
        \"\"\"
        with self._lock:
            # 主文件不存在时无需轮转（首次运行或刚刚完成上一次轮转后）
            if not self.log_file.exists():
                return
            # 文件大小未超过上限，无需轮转
            if self.log_file.stat().st_size < self.max_bytes:
                return

            # 执行文件轮转（倒序重命名，从最大序号往小遍历，避免先改小号导致大号被覆盖）
            # 例如：backup_count=5，range(4, 0, -1) = [4, 3, 2, 1]
            for i in range(self.backup_count - 1, 0, -1):
                src = self.log_dir / f"debug_trace.jsonl.{i}"
                dst = self.log_dir / f"debug_trace.jsonl.{i + 1}"
                if src.exists():
                    # os.replace 是原子操作，等价于 mv，避免 rename 时中途崩溃留下残缺文件
                    os.replace(src, dst)
            # 将当前主文件重命名为 .1，完成归档（旧的 .1 已在上面的循环中移到 .2）
            os.replace(self.log_file, self.log_dir / "debug_trace.jsonl.1")
            # 轮转完成后主文件 debug_trace.jsonl 不存在，下次 write_record 会自动创建"""

content = content.replace(rotate_text, replace_rotate_text)


with open("src/observability_hub/jsonl_storage.py", "w") as f:
    f.write(content)
