from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from src.observability_hub.recording import LogLevel, NormalizedRecord
from src.observability_hub.request_coloring import RequestColoringContext, RequestColoringState
from src.observability_hub.jsonl_storage import JSONLStorageEngine
from src.observability_hub.cli_logger import CLILogTailer

# ============================================================
# 全栈监控层 —— 模块导出容器 (Observability Hub Exports)
#
# 本文件是 T5 阶段对 ObservabilityHubExports 的扩展：
# 在原有的 trace_id_generator、record、is_request_colored 基础上，
# 新增了 jsonl_storage 和 cli_logger 两个 Optional 字段（T5 新增）。
#
# 设计模式：强类型导出容器（Typed Export Container）
#   各模块的 bootstrap 函数最终构造并返回一个 XXXExports 实例，
#   上层依赖方通过这个强类型对象访问能力，避免了直接 import 内部实现类。
#   这种模式的好处是：内部实现可以自由替换，只要导出接口不变，上层无需感知。
#
# T5 新增字段的接入状态：
#   jsonl_storage 和 cli_logger 默认为 None，当前 bootstrap.py 尚未注入实例，
#   上层调用方在使用前必须判空。详见审阅报告 [REV-T5-CON-003]。
# ============================================================


@dataclass(frozen=True)
class ObservabilityHubExports:
    """
    全栈监控与治理中心的强类型模块导出容器 (Observability Hub Exports)。

    设计意图：
        向外暴露 observability_hub 层的全部能力接口，使上层模块（如编排引擎、渠道层）
        可以通过统一的强类型对象访问监控能力，而无需直接 import 内部实现类。

    字段分为两组：
        - 核心能力（必填，T1/T2 阶段已有）：trace_id_generator, record, is_request_colored
        - 调试扩展（可选，T5 新增）：jsonl_storage, cli_logger

    Attributes:
        layer (str): 当前模块所属的架构层级名称（如 "observability_hub"）。
        status (str): 模块当前状态标识（如 "active" / "degraded"）。
        trace_id_generator (Callable[[], str]): 生成全局唯一 TraceID 的工厂函数。
        record (Callable[...]): 归一化日志打点接口，接受来自任意层的监控数据。
            签名：(trace_id: str, payload: Mapping|str|Any, level: LogLevel|str) -> NormalizedRecord
        is_request_colored (Callable[...]): 判断当前请求是否需要全量染色采集的接口。
            签名：(ctx: RequestColoringContext, state: RequestColoringState|None) -> bool
        jsonl_storage (JSONLStorageEngine | None): T5 新增。JSONL 调试日志存储引擎实例。
            为 None 表示 JSONL 存储功能未启用（当前 bootstrap 未注入）。
        cli_logger (CLILogTailer | None): T5 新增。CLI 实时日志工具实例。
            为 None 表示 CLI 日志功能未启用（当前 bootstrap 未注入）。
    """
    # ---- 核心能力字段（T1/T2 阶段已有，必填，无默认值）----
    layer: str                                    # 模块层级名称
    status: str                                   # 模块运行状态
    trace_id_generator: Callable[[], str]         # TraceID 生成器
    record: Callable[[str, Mapping[str, Any] | str | Any, LogLevel | str], NormalizedRecord]  # 日志打点入口
    is_request_colored: Callable[[RequestColoringContext, RequestColoringState | None], bool]  # 染色判定接口

    # ---- T5 新增扩展字段（Optional，默认 None，bootstrap 暂未注入）----
    jsonl_storage: JSONLStorageEngine | None = None  # JSONL 存储引擎，None 表示未启用
    cli_logger: CLILogTailer | None = None           # CLI 日志工具，None 表示未启用

