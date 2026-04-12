import json
import logging
import os
import time
import threading
from pathlib import Path
from src.observability_hub.recording import NormalizedRecord

# ============================================================
# 全栈监控层 —— JSONL 调试存储引擎 (JSONL Debug Storage Engine)
#
# 本模块实现了规格 OB-P0-04（调试引擎实现）和 OB-P0-05（滚动清理策略）。
#
# 为什么用 JSONL（JSON Lines）格式？
#   JSONL 是"每行一个 JSON 对象"的格式。相比普通 JSON，它的优势是：
#   1. 追加写入效率极高（只需 append，不需要读-改-写整个文件）。
#   2. 可以用 readline() 逐行流式读取，不需要把整个文件加载到内存。
#   3. 文件损坏时只影响损坏行，其余行仍然可读。
#
# 文件轮转策略（OB-P0-05）：
#   当日志文件超过 max_bytes 时，执行类似 logrotate 的文件重命名轮转：
#   debug_trace.jsonl → .1 → .2 → ... → .backup_count（最老的被覆盖丢弃）
#
# 局限性（P0 阶段）：
#   - 同步写入（不支持异步/批量写入），高频日志场景可能有 I/O 瓶颈。
#   - 文件轮转存在多线程竞态风险，详见审阅报告 [REV-OB0405-BUG-001]。
#   - 本模块未在 bootstrap.py 中实例化，是"已交付但未接入"的状态（REV-T5-CON-003）。
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

        注意：
            payload 字段的类型是 Any，json.dumps 可能因不可序列化的对象（如自定义类实例）
            而抛出 TypeError，当前的 except Exception 会捕获并静默记录，
            但调用方无法感知该条日志实际上没有写入。
        """
        # [修复 REV-OB0405-CON-001]
        # 将自检轮转和写入全部打包收拢进 try 块和互斥锁内。
        # 第一层防护（Lock）：避免高并发时由于同时到达大小上限，从而触发两次轮转重命名导致的竞态崩溃。
        # 第二层防护（try）：如果轮转时硬盘满了或者写入没有权限遭遇异常，这些观测域监控性质的意外绝不会
        # 反抛回给主业务程序去背黑锅，造成主系统的挂机（平滑丢弃或报警）。
        try:
            with self._lock:
                # 写入前先检查是否需要轮转（如果文件已超过 max_bytes，先轮转再写）
                self._rotate_if_needed()
                # 以追加模式（"a"）打开文件，每次调用只添加一行，不覆盖已有内容
                with open(self.log_file, "a", encoding="utf-8") as f:
                    # 将 NormalizedRecord 的核心字段序列化为字典
                    record_dict = {
                        "trace_id": record.trace_id,           # 请求链路唯一标识
                        "level": record.level.value,           # 日志级别（枚举值转字符串）
                        "payload": record.payload,             # 原始载荷（可能是 dict/str/任意对象）
                        "payload_type": record.payload_type,   # 载荷类型描述字符串
                        "timestamp_ms": record.timestamp_ms    # 毫秒级时间戳
                    }
                    # ensure_ascii=False 保证中文等非 ASCII 字符直接输出，不转义为 \uXXXX
                    f.write(json.dumps(record_dict, ensure_ascii=False) + "\n")
        except Exception as e:
            # 写入或轮转失败时降级处理：只记录错误日志，不抛异常，避免影响主业务流程
            # 注意：调用方无法感知本次写入失败，日志可能丢失
            logger.error(f"Failed to write JSONL log: {e}")

    def _rotate_if_needed(self) -> None:
        """
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
        """
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
        # 轮转完成后主文件 debug_trace.jsonl 不存在，下次 write_record 会自动创建

