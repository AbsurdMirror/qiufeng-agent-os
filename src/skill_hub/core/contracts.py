from dataclasses import dataclass, field
from typing import Any, Protocol

from src.orchestration_engine.contracts import (
    CapabilityDescription,
    CapabilityRequest,
    CapabilityResult,
)


@dataclass(frozen=True)
class BrowserUseRuntimeState:
    """
    browser-use 浏览器工具的最小运行时探测结果。
    """
    browser_use_installed: bool
    playwright_installed: bool
    available: bool
    status: str
    reason: str | None = None
    browser_use_version: str | None = None
    playwright_version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "browser_use_installed": self.browser_use_installed,
            "playwright_installed": self.playwright_installed,
            "available": self.available,
            "status": self.status,
            "reason": self.reason,
            "browser_use_version": self.browser_use_version,
            "playwright_version": self.playwright_version,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PyToolDefinition:
    """
    Skill Hub 内部单个 PyTools 的强类型定义。
    
    设计意图：
    将工具的能力描述（静态元数据）与运行时状态（动态探测结果）结合起来，
    形成一个完整的工具快照，方便做统一的管理和展示。
    """
    capability: CapabilityDescription
    runtime_state: BrowserUseRuntimeState
    metadata: dict[str, Any] = field(default_factory=dict)


class PyTool(Protocol):
    """
    Skill Hub 内部 PyTools 的最小统一协议 (Duck Typing Interface)。
    
    设计意图：
    任何想接入系统成为“工具”的 Python 类，都必须实现这个协议。
    它强制要求工具必须：
    1. 自带能力描述（我是谁，我能干什么）。
    2. 提供运行时探测（我的运行环境准备好了没）。
    3. 提供异步执行入口（接收标准请求，返回标准结果）。
    """
    capability: CapabilityDescription

    def probe_runtime(self) -> BrowserUseRuntimeState:
        """探测当前工具的运行时依赖是否满足"""
        raise NotImplementedError

    async def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        """异步执行工具逻辑"""
        raise NotImplementedError
