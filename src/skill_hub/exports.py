from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from src.orchestration_engine.contracts import (
    CapabilityDescription,
    CapabilityHub,
    CapabilityRequest,
    CapabilityResult,
)
from src.skill_hub.browser_use import BrowserUsePyTool
from src.skill_hub.contracts import BrowserUseRuntimeState


@dataclass(frozen=True)
class SkillHubExports:
    """
    技能与工具层 (Skill Hub) 的强类型导出对象。
    
    设计意图：
    把整个工具模块初始化后所有能对外提供的对象、代理方法全部打包在这个数据类里。
    这避免了返回一个模糊的字典 dict，使得其他模块（如 OrchestrationEngine）在调用时
    能享受完整的 IDE 代码补全和 mypy 静态类型检查。
    """
    layer: str
    status: str
    
    # 底层实例
    browser_pytool: BrowserUsePyTool
    # 统一能力中心（其中包含了所有的模型和工具）
    capability_hub: CapabilityHub
    
    # 快捷代理方法：操作整个能力中心
    list_capabilities: Callable[[], tuple[CapabilityDescription, ...]]
    get_capability: Callable[[str], CapabilityDescription | None]
    invoke_capability: Callable[[CapabilityRequest], Awaitable[CapabilityResult]]
    
    # 快捷代理方法：直接操作浏览器工具
    probe_browser_runtime: Callable[[], BrowserUseRuntimeState]
    invoke_browser: Callable[[CapabilityRequest], Awaitable[CapabilityResult]]
