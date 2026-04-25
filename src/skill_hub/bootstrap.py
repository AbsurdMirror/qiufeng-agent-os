from src.skill_hub.core.capability_hub import (
    RegisteredCapabilityHub,
)
from src.skill_hub.exports import SkillHubExports
from src.observability_hub.exports import ObservabilityHubExports


def initialize(observability: ObservabilityHubExports | None = None) -> SkillHubExports:
    """
    技能与工具层 (Skill Hub) 的初始化引导函数。
    
    设计意图：
    在应用启动时（被 `src.app.bootstrap` 调用），实例化全局的 `RegisteredCapabilityHub` 注册中心。
    本层仅负责初始化骨架，具体的模型与内置工具挂载由上层（如 QFAOS）根据用户配置决定。
    """
    # 实例化统一的能力注册中心
    capability_hub = RegisteredCapabilityHub(observability=observability)
    
    return SkillHubExports(
        layer="skill_hub",
        status="initialized",
        capability_hub=capability_hub,
        list_capabilities=capability_hub.list_capabilities,
        get_capability=capability_hub.get_capability,
        invoke_capability=capability_hub.invoke,
    )
