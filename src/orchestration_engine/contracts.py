from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class CapabilityDescription:
    """
    单个能力的标准化描述对象。

    设计意图：
    让编排层能够在不感知底层模型或工具实现差异的前提下，
    以统一元数据发现能力的调用入口、输入输出约束与附加属性。
    """
    capability_id: str
    domain: str
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CapabilityRequest:
    """
    编排层发起能力调用时的统一请求载体。
    """
    capability_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CapabilityResult:
    """
    能力调用的统一返回结构。
    """
    capability_id: str
    success: bool
    output: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class CapabilityHub(Protocol):
    """
    面向编排层暴露的统一能力访问协议。

    所有能力中心实现都必须支持：
    - 按 ID 获取能力描述
    - 枚举当前可见的能力列表
    - 以统一请求对象执行能力调用
    """
    def list_capabilities(self) -> tuple[CapabilityDescription, ...]:
        raise NotImplementedError

    def get_capability(self, capability_id: str) -> CapabilityDescription | None:
        raise NotImplementedError

    async def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        raise NotImplementedError


class NullCapabilityHub:
    """
    编排层默认挂载的空能力中心。

    在 T3 Task1 阶段用于占位与类型对齐，确保编排层已经具备明确的强类型契约，
    后续 Task5 再将真实的 Skill Hub 与模型能力路由注入进来。
    """
    def __init__(self, capabilities: tuple[CapabilityDescription, ...] = ()) -> None:
        self._capabilities = {
            capability.capability_id: capability
            for capability in capabilities
        }

    def list_capabilities(self) -> tuple[CapabilityDescription, ...]:
        return tuple(self._capabilities.values())

    def get_capability(self, capability_id: str) -> CapabilityDescription | None:
        return self._capabilities.get(capability_id)

    async def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        capability = self.get_capability(request.capability_id)
        if capability is None:
            return CapabilityResult(
                capability_id=request.capability_id,
                success=False,
                output={},
                error_code="capability_not_found",
                error_message=f"capability '{request.capability_id}' is not registered",
            )

        return CapabilityResult(
            capability_id=request.capability_id,
            success=False,
            output={},
            error_code="capability_not_implemented",
            error_message=f"capability '{request.capability_id}' is not implemented",
            metadata={"domain": capability.domain},
        )
