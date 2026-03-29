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
        return probe_browser_use_runtime()

    async def invoke(self, request: CapabilityRequest) -> CapabilityResult:
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
