from abc import ABC, abstractmethod

from src.channel_gateway.core.domain.events import UniversalEvent
from src.orchestration_engine.contracts import CapabilityHub
from src.orchestration_engine.context.runtime_context import RuntimeContext


class BaseOrchestrator(ABC):
    """
    智能体编排器的抽象基类 (Abstract Base Class)。
    
    设计意图：
    确立所有具体编排引擎（如基于 LangGraph、基于 LangChain 或自研状态机）的统一执行契约。
    强制所有编排器实现异步的 `execute` 方法，以接入外层的事件调度循环。
    
    初学者提示：
    继承了 ABC 且带有 @abstractmethod 的类不能被直接实例化。
    它就像是一个"模板"或"合同"，任何继承它的子类都必须自己写代码实现 `execute` 方法，
    否则 Python 会在运行时报错。这保证了所有编排器都有统一的入口。
    """
    @abstractmethod
    async def execute(
        self,
        event: UniversalEvent,
        ctx: RuntimeContext,
        capability_hub: CapabilityHub,
    ) -> dict[str, object]:
        """
        执行单次智能体编排逻辑。
        
        Args:
            event (UniversalEvent): 经过网关层解析的标准化触发事件（如用户输入）。
            ctx (RuntimeContext): 贯穿本次执行生命周期的上下文状态（例如记忆、会话ID等）。
            capability_hub (CapabilityHub): 注入的统一能力访问中心，负责编排层对模型与工具的发现和调用。
                
        Returns:
            dict[str, object]: 编排执行的最终结果或状态增量（通常用于更新上下文）。
        """
        raise NotImplementedError
