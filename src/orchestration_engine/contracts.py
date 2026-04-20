from typing import Protocol

from src.domain.capabilities import (
    CapabilityDescription,
    CapabilityRequest,
    CapabilityResult,
)


class CapabilityHub(Protocol):
    """
    面向编排层暴露的统一能力访问协议 (Protocol 鸭子类型接口)。

    所有能力中心实现都必须支持：
    - 按 ID 获取能力描述
    - 枚举当前可见的能力列表
    - 以统一请求对象执行能力调用
    
    只要一个类实现了这三个方法，Python 静态类型检查就会认为它是 CapabilityHub。
    """
    def list_capabilities(self) -> tuple[CapabilityDescription, ...]:
        """获取当前注册的所有能力描述的列表"""
        raise NotImplementedError

    def get_capability(self, capability_id: str) -> CapabilityDescription | None:
        """根据唯一标识符获取对应的能力描述，若不存在则返回 None"""
        raise NotImplementedError

    async def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        """异步执行能力调用，接收统一请求，返回统一结果"""
        raise NotImplementedError


class NullCapabilityHub:
    """
    编排层默认挂载的空能力中心 (Null Object Pattern)。

    在 T3 Task1 阶段用于占位与类型对齐，确保编排层已经具备明确的强类型契约，
    后续 Task5 再将真实的 Skill Hub 与模型能力路由注入进来。
    它的存在避免了到处判断 capability_hub is None 的繁琐逻辑。
    """
    def __init__(self, capabilities: tuple[CapabilityDescription, ...] = ()) -> None:
        # 将传入的能力元组转换为字典，以能力 ID 为键，方便快速查找
        self._capabilities = {
            capability.capability_id: capability
            for capability in capabilities
        }

    def list_capabilities(self) -> tuple[CapabilityDescription, ...]:
        # 返回当前空中心里注册的（通常为空）能力列表
        return tuple(self._capabilities.values())

    def get_capability(self, capability_id: str) -> CapabilityDescription | None:
        # 尝试获取指定 ID 的能力，不存在返回 None
        return self._capabilities.get(capability_id)

    async def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        # 尝试查找请求的能力
        capability = self.get_capability(request.capability_id)
        if capability is None:
            # 如果能力未注册，返回标准化的错误结果
            return CapabilityResult(
                capability_id=request.capability_id,
                success=False,
                output={},
                error_code="capability_not_found",
                error_message=f"capability '{request.capability_id}' is not registered",
            )

        # 即使能力注册了，空中心也没有具体的执行逻辑，返回未实现错误
        return CapabilityResult(
            capability_id=request.capability_id,
            success=False,
            output={},
            error_code="capability_not_implemented",
            error_message=f"capability '{request.capability_id}' is not implemented",
            metadata={"domain": capability.domain},
        )
