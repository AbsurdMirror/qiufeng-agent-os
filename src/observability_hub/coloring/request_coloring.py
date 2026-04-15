from collections.abc import Mapping, Set as AbstractSet
from dataclasses import dataclass
from typing import Any

RequestColoringContext = Mapping[str, Any]


@dataclass(frozen=True)
class RequestColoringState:
    """
    请求染色状态容器。
    
    设计意图：
    用于存储需要被“染色（即强制开启全量日志追踪或 Debug 模式）”的规则集合。
    通常由配置系统或远程下发，决定哪些特定的 trace_id 或 session_id 应当被染色。
    
    Attributes:
        trace_ids: 需要被染色的目标 trace_id 集合。
        session_ids: 需要被染色的目标 session_id 集合。
    """
    trace_ids: AbstractSet[str]
    session_ids: AbstractSet[str]


def is_request_colored(
    context: RequestColoringContext,
    state: RequestColoringState | None = None,
) -> bool:
    """
    判断当前请求是否命中染色规则。
    
    规则优先级：
    1. 显式指定：如果请求上下文中携带了 debug 标志（如 is_debug=True），直接染色。
    2. 匹配集合：如果请求的 trace_id 或 session_id 命中了 state 中配置的规则集合，则染色。
    3. 默认不染色。
    
    Args:
        context: 请求上下文，通常包含 trace_id, session_id 或显式的 debug 标志。
        state: 当前系统的染色规则配置。如果为 None，则仅依赖 context 中的显式标志。
        
    Returns:
        bool: 是否需要染色。
    """
    debug_value = _read_value(context, "is_debug", "isDebug", "debug")
    if _is_truthy(debug_value):
        return True
    trace_id = _read_value(context, "trace_id", "traceId")
    session_id = _read_value(context, "session_id", "sessionId")
    if state is None:
        return False
    if isinstance(trace_id, str) and trace_id in state.trace_ids:
        return True
    if isinstance(session_id, str) and session_id in state.session_ids:
        return True
    return False


def create_coloring_state(
    trace_ids: set[str] | None = None,
    session_ids: set[str] | None = None,
) -> RequestColoringState:
    """
    创建并冻结一个染色状态对象。
    为了保证线程安全，传入的 set 会被转换为不可变的 frozenset。
    """
    return RequestColoringState(
        trace_ids=frozenset(trace_ids or set()),
        session_ids=frozenset(session_ids or set()),
    )


def _read_value(context: RequestColoringContext, *keys: str) -> Any:
    """辅助函数：按顺序尝试从上下文中读取多个可能的键名"""
    for key in keys:
        if key in context:
            return context[key]
    return None


def _is_truthy(value: Any) -> bool:
    """辅助函数：宽容地将各种类型的值解析为布尔真值"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, int):
        return value != 0
    return False
