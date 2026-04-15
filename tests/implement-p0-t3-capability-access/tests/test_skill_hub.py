import asyncio

from src.model_provider.contracts import ModelRequest, ModelResponse
from src.orchestration_engine.contracts import CapabilityRequest
from src.skill_hub import initialize
from src.skill_hub.builtin_tools.browser_use import BrowserUsePyTool, probe_browser_use_runtime
from src.skill_hub.contracts import BrowserUseRuntimeState


def test_sh_01_initialize_exposes_browser_pytool_exports():
    """测试项 SH-01: Skill Hub 初始化暴露最小 browser PyTool 骨架"""
    exports = initialize()
    browser_capability = exports.get_capability("tool.browser.open")
    model_capability = exports.get_capability("model.chat.default")
    minimax_capability = exports.get_capability("model.minimax.chat")
    capability_ids = {capability.capability_id for capability in exports.list_capabilities()}

    assert exports.layer == "skill_hub"
    assert exports.status == "initialized"
    assert exports.capability_hub is not None
    assert browser_capability is not None
    assert model_capability is not None
    assert minimax_capability is not None
    assert capability_ids == {
        "tool.browser.open",
        "model.chat.default",
        "model.minimax.chat",
    }


def test_sh_02_probe_runtime_degrades_without_browser_use(monkeypatch):
    """测试项 SH-02: 缺失 browser-use 依赖时返回明确降级状态"""
    monkeypatch.setattr("src.skill_hub.builtin_tools.browser_use._has_dependency", lambda name: False)
    monkeypatch.setattr("src.skill_hub.builtin_tools.browser_use._read_dependency_version", lambda name: None)

    state = probe_browser_use_runtime()

    assert isinstance(state, BrowserUseRuntimeState)
    assert state.available is False
    assert state.status == "degraded"
    assert state.reason == "playwright_dependency_missing"
    assert state.to_dict()["browser_use_installed"] is False


def test_sh_03_browser_tool_returns_standard_result_when_runtime_unavailable(monkeypatch):
    """测试项 SH-03: 浏览器 PyTool 在降级态返回统一错误结果"""
    monkeypatch.setattr("src.skill_hub.builtin_tools.browser_use._has_dependency", lambda name: False)
    monkeypatch.setattr("src.skill_hub.builtin_tools.browser_use._read_dependency_version", lambda name: None)
    tool = BrowserUsePyTool()

    result = asyncio.run(
        tool.invoke(
            CapabilityRequest(
                capability_id="tool.browser.open",
                payload={"url": "https://example.com"},
            )
        )
    )

    assert result.capability_id == "tool.browser.open"
    assert result.success is False
    assert result.error_code == "browser_runtime_unavailable"
    assert result.output["accepted"] is False
    assert result.output["runtime"]["available"] is False


def test_sh_04_capability_hub_routes_tool_capability(monkeypatch):
    """测试项 SH-04: Skill Hub 统一入口可转发工具域能力"""
    monkeypatch.setattr("src.skill_hub.builtin_tools.browser_use._has_dependency", lambda name: False)
    monkeypatch.setattr("src.skill_hub.builtin_tools.browser_use._read_dependency_version", lambda name: None)
    exports = initialize()

    result = asyncio.run(
        exports.invoke_capability(
            CapabilityRequest(
                capability_id="tool.browser.open",
                payload={"url": "https://example.com"},
            )
        )
    )

    assert result.capability_id == "tool.browser.open"
    assert result.success is False
    assert result.error_code == "browser_runtime_unavailable"
    assert result.metadata["domain"] == "tool"


def test_sh_05_capability_hub_routes_model_capability_to_model_domain():
    """测试项 SH-05: Skill Hub 统一入口可转发模型域能力"""

    class FakeModelProviderClient:
        def invoke(self, request: ModelRequest) -> ModelResponse:
            assert request.model_tag == "model.minimax.chat"
            assert request.metadata["trace_id"] == "trace-sh-05"
            assert request.metadata["provider"] == "minimax"
            return ModelResponse(
                model_name="minimax/abab6.5s-chat",
                content="模型路由成功",
                finish_reason="stop",
                provider_id="minimax",
                raw={"status": "ok"},
            )

    exports = initialize(model_client=FakeModelProviderClient())

    result = asyncio.run(
        exports.invoke_capability(
            CapabilityRequest(
                capability_id="model.minimax.chat",
                payload={
                    "messages": [{"role": "user", "content": "你好"}],
                },
                metadata={"trace_id": "trace-sh-05"},
            )
        )
    )

    assert result.capability_id == "model.minimax.chat"
    assert result.success is True
    assert result.output["content"] == "模型路由成功"
    assert result.output["provider_id"] == "minimax"
    assert result.metadata["domain"] == "model"
