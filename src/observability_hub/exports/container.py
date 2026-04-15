from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ..record.recording import LogLevel, NormalizedRecord
from ..coloring.request_coloring import RequestColoringContext, RequestColoringState
from ..jsonl.storage import JSONLStorageEngine
from ..cli.tailer import CLILogTailer

# ============================================================
# 全栈监控层 —— 模块导出容器 (Observability Hub Exports)
# ============================================================


@dataclass(frozen=True)
class ObservabilityHubExports:
    """
    全栈监控与治理中心的强类型模块导出容器 (Observability Hub Exports)。

    设计意图：
        向外暴露 observability_hub 层的全部能力接口，使上层模块（如编排引擎、渠道层）
        可以通过统一的强类型对象访问监控能力，而无需直接 import 内部实现类。

    Attributes:
        layer (str): 当前模块所属的架构层级名称。
        status (str): 模块当前状态标识。
        trace_id_generator (Callable[[], str]): 生成全局唯一 TraceID 的工厂函数。
        record (Callable[...]): 归一化日志打点接口。
        is_request_colored (Callable[...]): 判断当前请求是否需要全量染色采集的接口。
        jsonl_storage (JSONLStorageEngine | None): JSONL 调试日志存储引擎实例。
        cli_logger (CLILogTailer | None): CLI 实时日志工具实例。
    """
    layer: str                                    # 模块层级名称
    status: str                                   # 模块运行状态
    trace_id_generator: Callable[[], str]         # TraceID 生成器
    record: Callable[[str, Mapping[str, Any] | str | Any, LogLevel | str], NormalizedRecord]  # 日志打点入口
    is_request_colored: Callable[[RequestColoringContext, RequestColoringState | None], bool]  # 染色判定接口

    # ---- Optional 扩展字段 ----
    jsonl_storage: JSONLStorageEngine | None = None  # JSONL 存储引擎
    cli_logger: CLILogTailer | None = None           # CLI 日志工具
