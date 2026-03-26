from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeContext:
    trace_id: str
    logic_id: str
    session_id: str
    memory: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)

    def get_state(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

    def set_state(self, key: str, value: Any) -> None:
        self.state[key] = value

    def snapshot(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "logic_id": self.logic_id,
            "session_id": self.session_id,
            "memory": dict(self.memory),
            "state": dict(self.state),
        }
