import inspect
from collections.abc import Callable
from typing import Any, Annotated

from pydantic import validate_call, Field

from src.orchestration_engine.contracts import (
    CapabilityDescription,
    CapabilityRequest,
    CapabilityResult,
)
from src.skill_hub.core.tool_parser import parse_doxygen_to_json_schema


class FunctionPyTool:
    """
    将普通的 Python 可调用对象适配为 SkillHub 兼容的 PyTool。
    
    它负责自动提取函数签名生成 JSON Schema，并处理异步调用转换。
    """

    @validate_call(config={"arbitrary_types_allowed": True})
    def __init__(
        self, 
        tool_id: Annotated[str, Field(description="工具的唯一 ID")], 
        func: Annotated[Callable[..., Any], Field(description="被标记为工具的 Python 函数")]
    ) -> None:
        """
        初始化工具适配器。
        
        Args:
            tool_id: 工具的唯一 ID。
            func: 被标记为工具的 Python 函数。
        """
        self._func = func
        self.capability = CapabilityDescription(
            capability_id=f"tool.{tool_id}",
            domain="tool",
            name=tool_id,
            description=(func.__doc__ or "").strip() or f"工具 {tool_id}",
            input_schema=parse_doxygen_to_json_schema(func),
            output_schema={"type": "object"},
        )

    @validate_call(config={"arbitrary_types_allowed": True})
    async def invoke(
        self, 
        request: Annotated[CapabilityRequest, Field(description="工具调用请求")]
    ) -> CapabilityResult:
        """
        异步调用底层函数。
        
        Args:
            request: 包含调用参数的请求对象。
            
        Returns:
            CapabilityResult: 工具执行结果。
        """
        payload = request.payload or {}
        result = self._func(**payload)
        if inspect.isawaitable(result):
            result = await result
        return CapabilityResult(
            capability_id=self.capability.capability_id,
            success=True,
            output={"result": result},
        )
