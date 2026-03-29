from src.model_provider import initialize as initialize_model_provider
from src.model_provider.contracts import ModelProviderClient
from src.orchestration_engine.contracts import CapabilityRequest, CapabilityResult
from src.skill_hub.browser_use import BrowserUsePyTool
from src.skill_hub.capability_hub import (
    ModelCapabilityRouter,
    RegisteredCapabilityHub,
    register_pytools,
)
from src.skill_hub.exports import SkillHubExports


def initialize(model_client: ModelProviderClient | None = None) -> SkillHubExports:
    browser_pytool = BrowserUsePyTool()
    resolved_model_client = model_client or initialize_model_provider().client
    capability_hub = RegisteredCapabilityHub()
    register_pytools(capability_hub, (browser_pytool,))
    ModelCapabilityRouter(resolved_model_client).register_into(capability_hub)
    return SkillHubExports(
        layer="skill_hub",
        status="initialized",
        browser_pytool=browser_pytool,
        capability_hub=capability_hub,
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
    return await browser_pytool.invoke(request)
