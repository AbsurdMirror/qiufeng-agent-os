import inspect
from collections.abc import Callable
from typing import Any, Annotated

from pydantic import validate_call, Field

from src.domain.capabilities import CapabilityDescription, CapabilityRequest, CapabilityResult
from src.domain.translators.schema_translator import SchemaTranslator


class FunctionPyTool:
    """
    将普通的 Python 可调用对象适配为 SkillHub 兼容的 PyTool。
    
    重构说明：
    不再包含复杂的反射逻辑，全量委托给 SchemaTranslator 处理元数据生成与数据转换。
    """

    @validate_call(config={"arbitrary_types_allowed": True})
    def __init__(
        self, 
        tool_id: Annotated[str, Field(description="工具的唯一 ID")], 
        func: Annotated[Callable[..., Any], Field(description="被标记为工具的 Python 函数")]
    ) -> None:
        self._func = func
        # 一键生成完整的能力描述
        self.capability = SchemaTranslator.func_to_capability_description(func, f"tool.{tool_id}")

    @validate_call(config={"arbitrary_types_allowed": True})
    async def invoke(
        self, 
        request: Annotated[CapabilityRequest, Field(description="工具调用请求")]
    ) -> CapabilityResult:
        try:
            # 1. 输入验证与转换 (聚合参数)
            params_obj = SchemaTranslator.validate_payload(self.capability.input_model, request.payload or {})
            
            # 2. 执行底层函数 (解包参数)
            result = self._func(**params_obj.model_dump())
            if inspect.isawaitable(result):
                result = await result
            
            # 3. 输出验证与归一化
            output = SchemaTranslator.serialize_instance(self.capability.output_model, result)
            
            return CapabilityResult(
                capability_id=self.capability.capability_id,
                success=True,
                output=output,
            )
        except Exception as exc:
            return CapabilityResult(
                capability_id=self.capability.capability_id,
                success=False,
                output={},
                error_code="tool_execution_error",
                error_message=str(exc),
            )
