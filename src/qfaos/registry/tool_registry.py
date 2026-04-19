from typing import Annotated, Dict, Tuple, Any

from pydantic import validate_call, Field

class ToolRegistry:
    """
    工具注册表，用于管理所有已注册的 SDK 工具（PyTool）。
    """

    def __init__(self) -> None:
        """
        初始化工具注册表。
        """
        self._tools: Dict[str, Any] = {}

    @validate_call
    def register(
        self, 
        tool_id: Annotated[str, Field(description="工具的唯一标识符")], 
        tool: Annotated[Any, Field(description="实现了 PyTool 协议的工具对象")]
    ) -> None:
        """
        在注册表中记录或覆盖一个工具。
        
        Args:
            tool_id: 工具 ID。
            tool: PyTool 对象。
        """
        self._tools[tool_id] = tool

    @validate_call
    def get(
        self, 
        tool_id: Annotated[str, Field(description="工具的唯一标识符")]
    ) -> Any | None:
        """
        根据 ID 获取对应的工具。
        
        Args:
            tool_id: 工具 ID。
            
        Returns:
            Any | None: 已注册的工具对象，若未注册则返回 None。
        """
        return self._tools.get(tool_id)

    def list_tools(self) -> Tuple[str, ...]:
        """
        获取当前已注册的所有工具 ID 列表。
        
        Returns:
            Tuple[str, ...]: 已注册工具 ID 的元组。
        """
        return tuple(self._tools.keys())
