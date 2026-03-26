from collections.abc import Mapping, Set as AbstractSet
from dataclasses import dataclass
from typing import Any

RequestColoringContext = Mapping[str, Any]


@dataclass(frozen=True)
class RequestColoringState:
    trace_ids: AbstractSet[str]
    session_ids: AbstractSet[str]


def is_request_colored(
    context: RequestColoringContext,
    state: RequestColoringState | None = None,
) -> bool:
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
    return RequestColoringState(
        trace_ids=frozenset(trace_ids or set()),
        session_ids=frozenset(session_ids or set()),
    )


def _read_value(context: RequestColoringContext, *keys: str) -> Any:
    for key in keys:
        if key in context:
            return context[key]
    return None


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, int):
        return value != 0
    return False
