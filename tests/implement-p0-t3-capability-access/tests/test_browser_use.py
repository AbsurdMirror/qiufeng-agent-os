import pytest
import types
import sys
from pathlib import Path

from src.orchestration_engine.contracts import CapabilityRequest
from src.skill_hub.builtin_tools.browser_use import BrowserUsePyTool


@pytest.fixture
def browser_tool():
    return BrowserUsePyTool()


def test_sh_br_02_validation_failure(browser_tool: BrowserUsePyTool, monkeypatch):
    """SH-BR-02: 参数校验失败"""
    # 模拟环境就绪
    monkeypatch.setattr("src.skill_hub.builtin_tools.browser_use.probe_browser_use_runtime", lambda: type("MockState", (), {"available": True, "to_dict": lambda self: {}, "status": "ready"})())
    
    # 异步方法的同步测试可以使用 asyncio.run 或 pytest-asyncio，这里由于内部逻辑简单，直接使用 async/await 也可以
    # 不过为了标准，我们用 pytest.mark.anyio
    pass


@pytest.mark.anyio
async def test_sh_br_02_validation_failure_async(browser_tool: BrowserUsePyTool, monkeypatch):
    monkeypatch.setattr("src.skill_hub.builtin_tools.browser_use.probe_browser_use_runtime", lambda: type("MockState", (), {"available": True, "to_dict": lambda self: {}, "status": "ready"})())
    
    # 不传 URL
    req = CapabilityRequest(capability_id="tool.browser.open", payload={}, metadata={})
    res = await browser_tool.invoke(req)
    
    assert res.success is False
    assert res.error_code == "invalid_browser_request"
    assert res.error_message == "missing_browser_url"


@pytest.mark.anyio
async def test_sh_br_03_probe_only_mode(browser_tool: BrowserUsePyTool, monkeypatch):
    """SH-BR-03: 仅探测模式"""
    monkeypatch.setattr("src.skill_hub.builtin_tools.browser_use.probe_browser_use_runtime", lambda: type("MockState", (), {"available": True, "to_dict": lambda self: {}, "status": "ready"})())
    
    req = CapabilityRequest(
        capability_id="tool.browser.open",
        payload={"url": "https://example.com", "probe_only": True},
        metadata={}
    )
    res = await browser_tool.invoke(req)
    
    assert res.success is True
    assert res.output["execution_mode"] == "probe_only"
    # 探测模式下不应该有 navigation 对象
    assert "navigation" not in res.output
    assert res.output["page_text"] == ""
    assert res.output["links"] == []
    assert res.output["blocked_by_captcha"] is False


@pytest.mark.anyio
async def test_sh_br_04_runtime_unavailable_returns_standard_error(browser_tool: BrowserUsePyTool, monkeypatch):
    """SH-BR-04: 运行时不可用时返回统一错误结果"""
    monkeypatch.setattr(
        "src.skill_hub.builtin_tools.browser_use.probe_browser_use_runtime",
        lambda: type(
            "MockState",
            (),
            {"available": False, "to_dict": lambda self: {"available": False}, "status": "degraded", "reason": "playwright_dependency_missing"},
        )(),
    )
    
    req = CapabilityRequest(
        capability_id="tool.browser.open",
        payload={"url": "https://example.com"},
        metadata={}
    )
    res = await browser_tool.invoke(req)
    
    assert res.success is False
    assert res.error_code == "browser_runtime_unavailable"
    assert res.error_message == "playwright_dependency_missing"
    assert res.output["accepted"] is False
    assert res.output["execution_mode"] == "probe_only"


@pytest.mark.anyio
async def test_sh_br_05_actions_mode_returns_text_links_and_captcha_flag(browser_tool: BrowserUsePyTool, monkeypatch, tmp_path: Path):
    """SH-BR-05: actions 模式能返回 page_text/links 并检测 captcha"""
    monkeypatch.setattr(
        "src.skill_hub.builtin_tools.browser_use.probe_browser_use_runtime",
        lambda: type("MockState", (), {"available": True, "to_dict": lambda self: {"available": True}, "status": "ready"})(),
    )

    class _FakeKeyboard:
        async def press(self, key: str) -> None:
            return None

    class _FakePage:
        def __init__(self) -> None:
            self.url = "https://example.com/"
            self.keyboard = _FakeKeyboard()

        async def goto(self, url: str, wait_until: str = "domcontentloaded") -> None:
            self.url = url

        async def click(self, selector: str) -> None:
            self.url = "https://wappass.baidu.com/static/captcha/tuxing_v2.html"

        async def fill(self, selector: str, text: str) -> None:
            return None

        async def press(self, selector: str, key: str) -> None:
            return None

        async def wait_for_timeout(self, ms: int) -> None:
            return None

        async def screenshot(self, path: str, full_page: bool = True) -> None:
            Path(path).write_bytes(b"fakepng")

        async def title(self) -> str:
            return "百度安全验证"

        async def inner_text(self, selector: str) -> str:
            return "captcha verify you are human"

        async def content(self) -> str:
            return "<html></html>"

        async def eval_on_selector_all(self, selector: str, script: str, limit: int):
            return [{"href": "https://deepseek.com/", "text": "DeepSeek 官网"}]

    class _FakeContext:
        def __init__(self) -> None:
            self._handlers = []

        def on(self, event_name: str, handler) -> None:
            self._handlers.append((event_name, handler))

        async def new_page(self) -> _FakePage:
            return _FakePage()

        async def close(self) -> None:
            return None

    class _FakeBrowser:
        async def new_context(self) -> _FakeContext:
            return _FakeContext()

        async def close(self) -> None:
            return None

    class _FakeChromium:
        async def launch(self, headless: bool = True) -> _FakeBrowser:
            return _FakeBrowser()

    class _FakePlaywright:
        def __init__(self) -> None:
            self.chromium = _FakeChromium()

    class _FakeAsyncPlaywright:
        async def __aenter__(self) -> _FakePlaywright:
            return _FakePlaywright()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    fake_async_api = types.SimpleNamespace(async_playwright=lambda: _FakeAsyncPlaywright())
    monkeypatch.setitem(sys.modules, "playwright.async_api", fake_async_api)

    req = CapabilityRequest(
        capability_id="tool.browser.open",
        payload={
            "url": "https://www.baidu.com/",
            "probe_only": False,
            "headless": True,
            "actions": [
                {"type": "goto", "url": "https://www.baidu.com/"},
                {"type": "click", "selector": "a"},
                {"type": "screenshot", "path": str(tmp_path / "s.png")},
            ],
            "extract_text": True,
            "extract_links": True,
            "extract_dom": False,
            "max_text_chars": 1000,
            "max_links": 5,
            "screenshot_dir": str(tmp_path),
        },
        metadata={},
    )
    res = await browser_tool.invoke(req)
    assert res.success is True
    assert res.output["execution_mode"] == "playwright"
    assert isinstance(res.output["page_text"], str) and res.output["page_text"]
    assert isinstance(res.output["links"], list) and len(res.output["links"]) >= 1
    assert res.output["blocked_by_captcha"] is True
    assert res.output["block_reason"] != ""
