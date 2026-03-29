from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from typing import Any

from src.orchestration_engine.contracts import (
    CapabilityDescription,
    CapabilityRequest,
    CapabilityResult,
)
from src.skill_hub.contracts import BrowserUseRuntimeState


def probe_browser_use_runtime() -> BrowserUseRuntimeState:
    """
    探测 browser-use 与 Playwright 的最小运行时可用性。
    
    设计意图：
    在实际启动笨重的无头浏览器之前，先快速检查当前 Python 环境里有没有安装必要的依赖包。
    这能避免在核心流程中突然抛出 `ModuleNotFoundError` 导致程序崩溃。
    
    缺点与漏洞风险 (已记录至草稿)：
    这种探测过于浅显。它只检查了 Python 包是否 `pip install` 了，
    但没有检查 Playwright 是否实际下载了浏览器二进制文件（例如是否执行过 `playwright install`）。
    这可能导致探测返回 `available=True`，但在真实调用时依然崩溃。
    """
    browser_use_installed = _has_dependency("browser_use")
    playwright_installed = _has_dependency("playwright")
    browser_use_version = _read_dependency_version("browser-use")
    playwright_version = _read_dependency_version("playwright")

    if browser_use_installed and playwright_installed:
        return BrowserUseRuntimeState(
            browser_use_installed=True,
            playwright_installed=True,
            available=True,
            status="ready",
            browser_use_version=browser_use_version,
            playwright_version=playwright_version,
            metadata={"provider": "browser_use"},
        )

    if not browser_use_installed:
        reason = "browser_use_dependency_missing"
    else:
        reason = "playwright_dependency_missing"

    return BrowserUseRuntimeState(
        browser_use_installed=browser_use_installed,
        playwright_installed=playwright_installed,
        available=False,
        status="degraded",
        reason=reason,
        browser_use_version=browser_use_version,
        playwright_version=playwright_version,
        metadata={"provider": "browser_use"},
    )


class BrowserUsePyTool:
    """
    最小可用的 browser-use 浏览器 PyTools 骨架。
    
    设计意图：
    将底层的 browser-use 库包装成我们系统内部统一的 `Capability` 契约格式。
    目前 T3 阶段仅提供了骨架和探测能力（dry_run），不真正启动浏览器，为后续 T4/T5 阶段留出接口。
    """
    def __init__(self) -> None:
        self.capability = CapabilityDescription(
            capability_id="tool.browser.open",
            domain="tool",
            name="browser_open",
            description="使用 browser-use 探测浏览器运行时并接收最小页面打开请求。",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "probe_only": {"type": "boolean"},
                },
                "additionalProperties": True,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "accepted": {"type": "boolean"},
                    "execution_mode": {"type": "string"},
                    "runtime": {"type": "object"},
                    "url": {"type": "string"},
                },
                "additionalProperties": True,
            },
            metadata={"provider": "browser_use", "kind": "pytool"},
        )

    def probe_runtime(self) -> BrowserUseRuntimeState:
        """代理方法，调用包级别的探测函数"""
        return probe_browser_use_runtime()

    async def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        """
        执行工具调用。
        
        初学者提示：
        注意这里的容错处理：即使运行时不可用，或者参数不合法（如缺 URL），
        它都不会 `raise Exception`，而是返回一个 `success=False` 的 `CapabilityResult`，
        这保证了上层调度器的稳定性。
        """
        runtime_state = self.probe_runtime()
        payload = dict(request.payload)
        url = _normalize_url(payload.get("url"))
        probe_only = bool(payload.get("probe_only", False))

        if probe_only:
            return CapabilityResult(
                capability_id=self.capability.capability_id,
                success=runtime_state.available,
                output={
                    "accepted": runtime_state.available,
                    "execution_mode": "probe_only",
                    "runtime": runtime_state.to_dict(),
                    "url": url,
                },
                error_code=None if runtime_state.available else "browser_runtime_unavailable",
                error_message=None if runtime_state.available else runtime_state.reason,
                metadata={"status": runtime_state.status, "provider": "browser_use"},
            )

        if not url:
            return CapabilityResult(
                capability_id=self.capability.capability_id,
                success=False,
                output={
                    "accepted": False,
                    "execution_mode": "validation",
                    "runtime": runtime_state.to_dict(),
                    "url": "",
                },
                error_code="invalid_browser_request",
                error_message="missing_browser_url",
                metadata={"status": runtime_state.status, "provider": "browser_use"},
            )

        if not runtime_state.available:
            return CapabilityResult(
                capability_id=self.capability.capability_id,
                success=False,
                output={
                    "accepted": False,
                    "execution_mode": "probe_only",
                    "runtime": runtime_state.to_dict(),
                    "url": url,
                },
                error_code="browser_runtime_unavailable",
                error_message=runtime_state.reason,
                metadata={"status": runtime_state.status, "provider": "browser_use"},
            )

        return CapabilityResult(
            capability_id=self.capability.capability_id,
            success=True,
            output={
                "accepted": True,
                "execution_mode": "dry_run",
                "runtime": runtime_state.to_dict(),
                "url": url,
                "navigation": {
                    "provider": "browser_use",
                    "status": "accepted",
                },
            },
            metadata={"status": runtime_state.status, "provider": "browser_use"},
        )


def _has_dependency(module_name: str) -> bool:
    return find_spec(module_name) is not None


def _read_dependency_version(package_name: str) -> str | None:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return None


def _normalize_url(raw_url: Any) -> str:
    if raw_url is None:
        return ""
    return str(raw_url).strip()
