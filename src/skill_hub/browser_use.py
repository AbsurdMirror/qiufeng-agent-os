from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from pathlib import Path
import time
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
    """
    browser_use_installed = _has_dependency("browser_use")
    playwright_installed = _has_dependency("playwright")
    browser_use_version = _read_dependency_version("browser-use")
    playwright_version = _read_dependency_version("playwright")
    
    if playwright_installed:
        return BrowserUseRuntimeState(
            browser_use_installed=browser_use_installed,
            playwright_installed=True,
            available=True,
            status="ready",
            browser_use_version=browser_use_version,
            playwright_version=playwright_version,
            metadata={"provider": "playwright", "browser_use_installed": browser_use_installed, "browser_available": True},
        )
    
    return BrowserUseRuntimeState(
        browser_use_installed=browser_use_installed,
        playwright_installed=False,
        available=False,
        status="degraded",
        reason="playwright_dependency_missing",
        browser_use_version=browser_use_version,
        playwright_version=playwright_version,
        metadata={"provider": "playwright", "browser_available": False},
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
            description="使用 Playwright 启动浏览器访问网页并返回可观测产物（URL/Title/截图）。",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "probe_only": {"type": "boolean"},
                    "headless": {"type": "boolean"},
                    "browser_type": {"type": "string", "enum": ["chromium", "firefox", "webkit"]},
                    "click_selector": {"type": "string"},
                    "wait_ms": {"type": "integer"},
                    "screenshot_dir": {"type": "string"},
                    "actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "url": {"type": "string"},
                                "selector": {"type": "string"},
                                "text": {"type": "string"},
                                "key": {"type": "string"},
                                "wait_ms": {"type": "integer"},
                                "path": {"type": "string"},
                            },
                            "additionalProperties": True,
                        },
                    },
                    "extract_text": {"type": "boolean"},
                    "max_text_chars": {"type": "integer"},
                    "extract_dom": {"type": "boolean"},
                    "max_dom_chars": {"type": "integer"},
                    "extract_links": {"type": "boolean"},
                    "max_links": {"type": "integer"},
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
                    "url_before": {"type": "string"},
                    "url_after": {"type": "string"},
                    "title_before": {"type": "string"},
                    "title_after": {"type": "string"},
                    "screenshot_path": {"type": "string"},
                    "page_text": {"type": "string"},
                    "dom_summary": {"type": "string"},
                    "links": {"type": "array"},
                    "blocked_by_captcha": {"type": "boolean"},
                    "block_reason": {"type": "string"},
                },
                "additionalProperties": True,
            },
            metadata={"provider": "playwright", "kind": "pytool"},
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
        headless = bool(payload.get("headless", True))
        browser_type = payload.get("browser_type", "chromium")
        if browser_type not in ["chromium", "firefox", "webkit"]:
            browser_type = "chromium"
        click_selector = payload.get("click_selector")
        if click_selector is not None:
            click_selector = str(click_selector)
        wait_ms = payload.get("wait_ms")
        if wait_ms is None:
            wait_ms_value = 0
        else:
            try:
                wait_ms_value = int(wait_ms)
            except (TypeError, ValueError):
                wait_ms_value = 0
        screenshot_dir = payload.get("screenshot_dir")
        if screenshot_dir is None or not str(screenshot_dir).strip():
            screenshot_dir_value = "tests/implement-p0-t3-capability-access/artifacts/browser_playwright"
        else:
            screenshot_dir_value = str(screenshot_dir).strip()
        actions = _normalize_actions(payload.get("actions"))
        extract_text = bool(payload.get("extract_text", True))
        extract_dom = bool(payload.get("extract_dom", False))
        extract_links = bool(payload.get("extract_links", True))
        max_text_chars = _normalize_int(payload.get("max_text_chars"), 8000)
        max_dom_chars = _normalize_int(payload.get("max_dom_chars"), 8000)
        max_links = _normalize_int(payload.get("max_links"), 30)

        if probe_only:
            return CapabilityResult(
                capability_id=self.capability.capability_id,
                success=runtime_state.available,
                output={
                    "accepted": runtime_state.available,
                    "execution_mode": "probe_only",
                    "runtime": runtime_state.to_dict(),
                    "url": url,
                    "url_before": "",
                    "url_after": "",
                    "title_before": "",
                    "title_after": "",
                    "screenshot_path": "",
                    "page_text": "",
                    "dom_summary": "",
                    "links": [],
                    "blocked_by_captcha": False,
                    "block_reason": "",
                },
                error_code=None if runtime_state.available else "browser_runtime_unavailable",
                error_message=None if runtime_state.available else runtime_state.reason,
                metadata={"status": runtime_state.status, "provider": "playwright"},
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
                    "url_before": "",
                    "url_after": "",
                    "title_before": "",
                    "title_after": "",
                    "screenshot_path": "",
                    "page_text": "",
                    "dom_summary": "",
                    "links": [],
                    "blocked_by_captcha": False,
                    "block_reason": "",
                },
                error_code="invalid_browser_request",
                error_message="missing_browser_url",
                metadata={"status": runtime_state.status, "provider": "playwright"},
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
                    "url_before": "",
                    "url_after": "",
                    "title_before": "",
                    "title_after": "",
                    "screenshot_path": "",
                    "page_text": "",
                    "dom_summary": "",
                    "links": [],
                    "blocked_by_captcha": False,
                    "block_reason": "",
                },
                error_code="browser_runtime_unavailable",
                error_message=runtime_state.reason,
                metadata={"status": runtime_state.status, "provider": "playwright"},
            )

        try:
            from playwright.async_api import async_playwright
        except Exception as error:
            return CapabilityResult(
                capability_id=self.capability.capability_id,
                success=False,
                output={
                    "accepted": False,
                    "execution_mode": "playwright_import",
                    "runtime": runtime_state.to_dict(),
                    "url": url,
                    "url_before": "",
                    "url_after": "",
                    "title_before": "",
                    "title_after": "",
                    "screenshot_path": "",
                    "page_text": "",
                    "dom_summary": "",
                    "links": [],
                    "blocked_by_captcha": False,
                    "block_reason": "",
                },
                error_code="browser_runtime_unavailable",
                error_message=str(error),
                metadata={"status": runtime_state.status, "provider": "playwright"},
            )

        url_before = url
        url_after = ""
        title_before = ""
        title_after = ""
        screenshot_path = ""
        page_text = ""
        dom_summary = ""
        links: list[dict[str, str]] = []
        blocked_by_captcha = False
        block_reason = ""
        try:
            screenshot_root = Path(screenshot_dir_value)
            screenshot_root.mkdir(parents=True, exist_ok=True)
            screenshot_path = str(screenshot_root / f"screenshot_{int(time.time())}.png")
            async with async_playwright() as p:
                if browser_type == "firefox":
                    browser = await p.firefox.launch(headless=headless)
                elif browser_type == "webkit":
                    browser = await p.webkit.launch(headless=headless)
                else:
                    browser = await p.chromium.launch(headless=headless)
                context = await browser.new_context()
                opened_pages: list[Any] = []
                context.on("page", lambda new_page: opened_pages.append(new_page))
                page = await context.new_page()

                if actions:
                    await _run_actions(page=page, actions=actions, default_screenshot_path=screenshot_path)
                else:
                    await page.goto(url, wait_until="domcontentloaded")
                    if click_selector:
                        await page.click(click_selector)
                    if wait_ms_value > 0:
                        await page.wait_for_timeout(wait_ms_value)
                    await page.screenshot(path=screenshot_path, full_page=True)

                if opened_pages:
                    page = opened_pages[-1]

                url_after = page.url
                title_after = await page.title()
                title_before = title_before or title_after

                if extract_text:
                    page_text = await _safe_body_text(page)
                    page_text = page_text[:max_text_chars]
                if extract_dom:
                    dom_summary = await _safe_dom_content(page)
                    dom_summary = dom_summary[:max_dom_chars]
                if extract_links:
                    links = await _safe_links(page, limit=max_links)
                blocked_by_captcha, block_reason = _detect_block(title=title_after, text=page_text)

                await context.close()
                await browser.close()
        except Exception as error:
            return CapabilityResult(
                capability_id=self.capability.capability_id,
                success=False,
                output={
                    "accepted": False,
                    "execution_mode": "playwright",
                    "runtime": runtime_state.to_dict(),
                    "url": url,
                    "url_before": url_before,
                    "url_after": url_after,
                    "title_before": title_before,
                    "title_after": title_after,
                    "screenshot_path": screenshot_path,
                    "page_text": page_text,
                    "dom_summary": dom_summary,
                    "links": links,
                    "blocked_by_captcha": blocked_by_captcha,
                    "block_reason": block_reason,
                },
                error_code="browser_execution_failed",
                error_message=str(error),
                metadata={"status": runtime_state.status, "provider": "playwright"},
            )

        return CapabilityResult(
            capability_id=self.capability.capability_id,
            success=True,
            output={
                "accepted": True,
                "execution_mode": "playwright",
                "runtime": runtime_state.to_dict(),
                "url": url,
                "url_before": url_before,
                "url_after": url_after,
                "title_before": title_before,
                "title_after": title_after,
                "screenshot_path": screenshot_path,
                "page_text": page_text,
                "dom_summary": dom_summary,
                "links": links,
                "blocked_by_captcha": blocked_by_captcha,
                "block_reason": block_reason,
                "navigation": {
                    "provider": "playwright",
                    "status": "accepted",
                    "browser_type": browser_type,
                },
            },
            metadata={"status": runtime_state.status, "provider": "playwright", "browser_type": browser_type},
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


def _normalize_int(value: Any, default_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default_value
    if parsed <= 0:
        return default_value
    return parsed


def _normalize_actions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            normalized.append(dict(item))
    return normalized


async def _run_actions(page: Any, actions: list[dict[str, Any]], default_screenshot_path: str) -> None:
    for action in actions:
        action_type = str(action.get("type", "")).strip().lower()
        if action_type == "goto":
            url = _normalize_url(action.get("url"))
            if url:
                await page.goto(url, wait_until="domcontentloaded")
            continue
        if action_type == "click":
            selector = action.get("selector")
            if selector is not None:
                await page.click(str(selector))
            continue
        if action_type == "fill":
            selector = action.get("selector")
            text = action.get("text")
            if selector is not None:
                await page.fill(str(selector), "" if text is None else str(text))
            continue
        if action_type == "press":
            key = action.get("key")
            selector = action.get("selector")
            if key is None:
                continue
            if selector is None:
                await page.keyboard.press(str(key))
            else:
                await page.press(str(selector), str(key))
            continue
        if action_type == "wait":
            ms = _normalize_int(action.get("wait_ms"), 0)
            if ms > 0:
                await page.wait_for_timeout(ms)
            continue
        if action_type == "screenshot":
            path = action.get("path")
            screenshot_path = default_screenshot_path if path is None else str(path)
            await page.screenshot(path=screenshot_path, full_page=True)
            continue


async def _safe_body_text(page: Any) -> str:
    try:
        return await page.inner_text("body")
    except Exception:
        return ""


async def _safe_dom_content(page: Any) -> str:
    try:
        return await page.content()
    except Exception:
        return ""


async def _safe_links(page: Any, limit: int) -> list[dict[str, str]]:
    if limit <= 0:
        return []
    try:
        result = await page.eval_on_selector_all(
            "a[href]",
            "els => els.slice(0, limit).map(e => ({href: e.href, text: (e.innerText||'').trim()}))",
            limit,
        )
    except Exception:
        return []
    if not isinstance(result, list):
        return []
    links: list[dict[str, str]] = []
    for item in result:
        if not isinstance(item, dict):
            continue
        href = item.get("href")
        text = item.get("text")
        if isinstance(href, str) and href:
            links.append(
                {
                    "href": href,
                    "text": text if isinstance(text, str) else "",
                }
            )
    return links


def _detect_block(title: str, text: str) -> tuple[bool, str]:
    haystack = f"{title}\n{text}".lower()
    keywords = [
        "安全验证",
        "验证码",
        "captcha",
        "verify you are human",
        "robot",
        "人机验证",
        "验证",
        "security check",
        "prove you are not a robot",
        "reCAPTCHA",
        "图形验证",
        "滑动验证",
        "拼图验证",
        "点选验证",
        "短信验证",
        "邮件验证",
        "身份验证",
        "请完成验证",
        "verification code",
        "security verification",
    ]
    for keyword in keywords:
        if keyword.lower() in haystack:
            return True, keyword
    return False, ""
