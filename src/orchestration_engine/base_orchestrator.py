from abc import ABC, abstractmethod
from typing import Any

from src.channel_gateway.events import UniversalEvent
from src.orchestration_engine.runtime_context import RuntimeContext


class BaseOrchestrator(ABC):
    """
    智能体编排器的抽象基类 (Abstract Base Class)。
    
    设计意图：
    确立所有具体编排引擎（如基于 LangGraph、基于 LangChain 或自研状态机）的统一执行契约。
    强制所有编排器实现异步的 `execute` 方法，以接入外层的事件调度循环。
    """
    @abstractmethod
    async def execute(
        self,
        event: UniversalEvent,
        ctx: RuntimeContext,
        capability_hub: Any,
    ) -> dict[str, Any]:
        """
        执行单次智能体编排逻辑。
        
        Args:
            event (UniversalEvent): 经过网关层解析的标准化触发事件（如用户输入）。
            ctx (RuntimeContext): 贯穿本次执行生命周期的上下文状态。
            capability_hub (Any): 注入的底层能力集合（如模型调用、工具集等）。
                此处由于 P0 阶段尚未实现完整的 SkillHub，暂用 Any 占位。
                
        Returns:
            dict[str, Any]: 编排执行的最终结果或状态增量。
        """
        raise NotImplementedError

