import json
import logging
import os
import time
import threading
from pathlib import Path
from ..record.recording import NormalizedRecord
from src.domain.errors import format_user_facing_error

# ============================================================
# 全栈监控层 —— JSONL 调试存储引擎 (JSONL Debug Storage Engine)
#
# 本模块实现了规格 OB-P0-04（调试引擎实现）和 OB-P0-05（滚动清理策略）。
# ============================================================

logger = logging.getLogger(__name__)


class JSONLStorageEngine:
    """
    JSONL 格式的调试日志存储引擎 (OB-P0-04, OB-P0-05)。

    设计意图：
        将监控层归一化后的 NormalizedRecord 持久化写入 JSONL 文件，
        供 CLILogTailer 实时读取和 TraceID 过滤。
        同时实现基于文件大小的日志滚动（Rolling Rotation），防止日志文件无限增大。

    Args:
        log_dir (str): 日志目录路径，不存在时会自动创建。默认为 "logs"。
        max_bytes (int): 单个日志文件的最大字节数，超出后触发轮转。默认 10 MB。
        backup_count (int): 保留的历史备份文件数量。超出的最老文件会被覆盖丢弃。默认 5 个。

    写入文件：
        主文件：<log_dir>/debug_trace.jsonl
        备份：  <log_dir>/debug_trace.jsonl.1 ~ debug_trace.jsonl.<backup_count>
    """
    def __init__(self, log_dir: str = "logs", max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5):
        self.log_dir = Path(log_dir)
        # 确保日志目录存在，parents=True 支持多级目录，exist_ok=True 避免已存在时报错
        self.log_dir.mkdir(parents=True, exist_ok=True)
        # 固定主日志文件名，CLILogTailer 默认读取此路径
        self.log_file = self.log_dir / "debug_trace.jsonl"
        self.max_bytes = max_bytes       # 单文件大小上限（字节），超出触发轮转
        self.backup_count = backup_count # 保留历史备份文件的最大数量
        self._lock = threading.Lock()    # 用于保护文件轮转与写入的并发锁

    def write_record(self, record: NormalizedRecord) -> None:
        """
        将一条 NormalizedRecord 追加写入 JSONL 日志文件。

        执行流程：
            1. 先调用 _rotate_if_needed() 检查是否需要轮转（写前轮转策略）。
            2. 将 NormalizedRecord 序列化为字典并以 JSON 格式追加到文件末尾。
            3. 写入失败时仅记录错误日志，不向调用方抛出异常（降级容错）。

        Args:
            record (NormalizedRecord): 已归一化的监控记录，由 observability_hub.recording 定义。
        """
        try:
            # 将 NormalizedRecord 的核心字段序列化为字典
            record_dict = {
                "trace_id": record.trace_id,           # 请求链路唯一标识
                "level": record.level.value,           # 日志级别（枚举值转字符串）
                "payload": record.payload,             # 原始载荷（可能是 dict/str/任意对象）
                "payload_type": record.payload_type,   # 载荷类型描述字符串
                "timestamp_ms": record.timestamp_ms    # 毫秒级时间戳
            }
            # ensure_ascii=False 保证中文等非 ASCII 字符直接输出，不转义为 \uXXXX
            line = json.dumps(record_dict, ensure_ascii=False) + "\n"

            with self._lock:
                # 写入前先检查是否需要轮转（如果文件已超过 max_bytes，先轮转再写）
                self._rotate_if_needed()
                # 以追加模式（"a"）打开文件，每次调用只添加一行，不覆盖已有内容
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(line)
        except Exception as exc:
            # 写入或轮转失败时降级处理：只记录错误日志，不抛异常，避免影响主业务流程
            logger.error(
                format_user_facing_error(exc, summary=f"Failed to write JSONL log: {record}")
                )

    def _rotate_if_needed(self) -> None:
        """
        检查主日志文件是否超过大小上限，超出则执行文件轮转（Rolling Rotation）。
        """
        try:
            # 主文件不存在时无需轮转（首次运行或刚刚完成上一次轮转后）
            if not self.log_file.exists():
                return
            # 文件大小未超过上限，无需轮转
            if self.log_file.stat().st_size < self.max_bytes:
                return

            # 执行文件轮转（倒序重命名，从最大序号往小遍历，避免先改小号导致大号被覆盖）
            for i in range(self.backup_count - 1, 0, -1):
                src = self.log_dir / f"debug_trace.jsonl.{i}"
                dst = self.log_dir / f"debug_trace.jsonl.{i + 1}"
                if src.exists():
                    # os.replace 是原子操作，等价于 mv，避免 rename 时中途崩溃留下残缺文件
                    os.replace(src, dst)
            # 将当前主文件重命名为 .1，完成归档（旧的 .1 已在上面的循环中移到 .2）
            try:
                os.replace(self.log_file, self.log_dir / "debug_trace.jsonl.1")
            except PermissionError as pe:
                # 捕获 Windows 下常见的文件占用问题
                logger.warning(f"File in use, retrying rotation in 100ms... ({pe})")
                time.sleep(0.1)
                os.replace(self.log_file, self.log_dir / "debug_trace.jsonl.1")
                
        except Exception as e:
            # 即使轮转失败，也不能抛出异常阻断正常写入
            logger.warning(f"Failed to rotate JSONL file {self.log_file}: {e}")
