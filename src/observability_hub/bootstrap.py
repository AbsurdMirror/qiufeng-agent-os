from collections.abc import Mapping
from typing import Any
from .exports import ObservabilityHubExports
from .trace.id_generator import generate_trace_id
from .record.recording import record, LogLevel, NormalizedRecord
from .coloring.request_coloring import is_request_colored
from .jsonl.storage import JSONLStorageEngine
from .cli.tailer import CLILogTailer

def initialize(
    jsonl_log_dir: str = "logs",
    jsonl_max_bytes: int = 10 * 1024 * 1024,
    jsonl_backup_count: int = 5,
) -> ObservabilityHubExports:
    """
    全栈监控与治理中心 (Observability Hub) 的初始化引导函数。
    
    此函数会被 `src.app.bootstrap` 在应用启动时调用。它负责：
    将该层暴露的核心能力（如全局 TraceID 生成器、归一化数据采集接口、请求染色判定）
    打包并注册到全局的 Application 上下文中。
    
    Returns:
        ObservabilityHubExports: 包含该层所有关键实例和方法引用的强类型数据类
    """
    # [修复 REV-OBEXPORTS-CON-001]
    # 在模块点火阶段实例化最新的 JSONL 和 CLI 日志记录引擎。
    jsonl_storage = JSONLStorageEngine(
        log_dir=jsonl_log_dir,
        max_bytes=jsonl_max_bytes,
        backup_count=jsonl_backup_count,
    )
    cli_logger = CLILogTailer(log_file=str(jsonl_storage.log_file))

    def record_and_persist(
        trace_id: str,
        data: Mapping[str, Any] | str | Any,
        level: LogLevel | str = LogLevel.INFO,
    ) -> NormalizedRecord:
        """
        包装后的 record 函数：不仅进行归一化，还自动写入持久化存储。
        """
        normalized = record(trace_id, data, level)
        jsonl_storage.write_record(normalized)
        return normalized

    return ObservabilityHubExports(
        layer="observability_hub",
        status="initialized",
        trace_id_generator=generate_trace_id,
        record=record_and_persist,
        is_request_colored=is_request_colored,
        jsonl_storage=jsonl_storage,
        cli_logger=cli_logger,
    )
