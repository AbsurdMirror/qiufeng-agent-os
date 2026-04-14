from src.model_provider import initialize as initialize_model_provider
from src.model_provider.contracts import ModelProviderClient
from src.orchestration_engine.contracts import CapabilityRequest, CapabilityResult
from src.skill_hub.builtin_tools.browser_use import BrowserUsePyTool
from src.skill_hub.core.capability_hub import (
    ModelCapabilityRouter,
    RegisteredCapabilityHub,
    register_pytools,
)
from src.skill_hub.core.exports import SkillHubExports


def initialize(model_client: ModelProviderClient | None = None) -> SkillHubExports:
    """
    技能与工具层 (Skill Hub) 的初始化引导函数。
    
    设计意图：
    在应用启动时（被 `src.app.bootstrap` 调用），负责实例化所有的内置工具（如 BrowserUsePyTool），
    并创建一个全局的 `RegisteredCapabilityHub` 注册中心。
    它将模型客户端和工具全部注册到这个中心里，最后打包成强类型的 `SkillHubExports` 供编排层使用。
    """
    browser_pytool = BrowserUsePyTool()
    # 如果外层没有传入 model_client，则自行初始化模型层。这是一种防御性设计。
    resolved_model_client = model_client or initialize_model_provider().client
    
    # 实例化统一的能力注册中心
    capability_hub = RegisteredCapabilityHub()
    
    # 将浏览器工具注册到能力中心
    register_pytools(capability_hub, (browser_pytool,))
    # 将模型路由（包含各种模型能力）注册到能力中心
    ModelCapabilityRouter(resolved_model_client).register_into(capability_hub)
    
    return SkillHubExports(
        layer="skill_hub",
        status="initialized",
        browser_pytool=browser_pytool,
        capability_hub=capability_hub,
        # 提供代理方法，方便外层直接调用能力中心的 API
        list_capabilities=capability_hub.list_capabilities,
        get_capability=capability_hub.get_capability,
        probe_browser_runtime=browser_pytool.probe_runtime,
        invoke_browser=lambda request: _invoke_browser(
            browser_pytool=browser_pytool,
            request=request,
        ),
        invoke_capability=capability_hub.invoke,
    )


async def _invoke_browser(
    browser_pytool: BrowserUsePyTool,
    request: CapabilityRequest,
) -> CapabilityResult:
    """代理方法：用于执行浏览器工具的异步调用"""
    return await browser_pytool.invoke(request)
