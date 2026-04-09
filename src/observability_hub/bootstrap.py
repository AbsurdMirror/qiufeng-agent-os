from src.observability_hub.exports import ObservabilityHubExports
from src.observability_hub.recording import generate_trace_id, record
from src.observability_hub.request_coloring import is_request_colored
from src.observability_hub.jsonl_storage import JSONLStorageEngine
from src.observability_hub.cli_logger import CLILogTailer

def initialize() -> ObservabilityHubExports:
    """
    全栈监控与治理中心 (Observability Hub) 的初始化引导函数。
    
    此函数会被 `src.app.bootstrap` 在应用启动时调用。它负责：
    将该层暴露的核心能力（如全局 TraceID 生成器、归一化数据采集接口、请求染色判定）
    打包并注册到全局的 Application 上下文中。
    
    Returns:
        ObservabilityHubExports: 包含该层所有关键实例和方法引用的强类型数据类
    """
    jsonl_storage = JSONLStorageEngine()
    cli_logger = CLILogTailer()

    return ObservabilityHubExports(
        layer="observability_hub",
        status="initialized",
        trace_id_generator=generate_trace_id,
        record=record,
        is_request_colored=is_request_colored,
        jsonl_storage=jsonl_storage,
        cli_logger=cli_logger,
    )

