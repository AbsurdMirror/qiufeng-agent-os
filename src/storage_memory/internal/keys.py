def _build_hot_key(logic_id: str, session_id: str) -> str:
    """构建用于存储热记忆列表的唯一键名"""
    return f"hot_memory:{logic_id}:{session_id}"


def _build_state_key(logic_id: str, session_id: str) -> str:
    """构建用于存储运行时状态字典的唯一键名"""
    return f"runtime_state:{logic_id}:{session_id}"


def _build_sys_key(logic_id: str, session_id: str) -> str:
    """构建用于存储系统提示词片段的唯一键名"""
    return f"system_parts:{logic_id}:{session_id}"
