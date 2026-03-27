from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeContext:
    """
    编排引擎执行时的运行时上下文 (Runtime Context)。
    
    设计意图：
    贯穿 Agent 单次执行生命周期的状态容器，承载了追踪信息、业务标识以及运行期动态数据。
    
    Attributes:
        trace_id (str): 全链路追踪 ID，用于串联单次请求的所有打点日志。
        logic_id (str): 业务逻辑 ID，通常指代当前运行的 Agent ID。
        session_id (str): 会话 ID，用于区分多轮对话的用户上下文。
        memory (dict[str, Any]): 历史记忆数据的只读视图快照。
        state (dict[str, Any]): 当前执行图 (Graph) 中的动态状态变量容器。
    """
    trace_id: str
    logic_id: str
    session_id: str
    memory: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)

    def get_state(self, key: str, default: Any = None) -> Any:
        """安全地从当前上下文中读取状态变量"""
        return self.state.get(key, default)

    def set_state(self, key: str, value: Any) -> None:
        """更新当前上下文中的状态变量"""
        self.state[key] = value

    def snapshot(self) -> dict[str, Any]:
        """
        生成当前上下文的深拷贝快照。
        用于在持久化或快照回滚时，防止引用类型被意外篡改。
        """
        return {
            "trace_id": self.trace_id,
            "logic_id": self.logic_id,
            "session_id": self.session_id,
            "memory": dict(self.memory),
            "state": dict(self.state),
        }

