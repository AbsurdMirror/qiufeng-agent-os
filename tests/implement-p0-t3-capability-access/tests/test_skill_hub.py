import asyncio

from src.domain.models import ModelMessage, ModelResponse
from src.domain.capabilities import CapabilityRequest
from typing import Any
from src.skill_hub import initialize
from src.skill_hub.builtin_tools.browser_use import BrowserUsePyTool
from src.skill_hub.core.capability_hub import register_pytools
from src.model_provider.routing.router import ModelRouter


def test_sh_01_initialize_exposes_browser_pytool_exports():
    """测试项 SH-01: Skill Hub 初始化暴露最小 browser PyTool 骨架"""
    exports = initialize()
    hub = exports.capability_hub
    
    # 手动注册以适配新架构
    register_pytools(hub, (BrowserUsePyTool(),))
    router = ModelRouter(clients={})
    hub.register_instance_capabilities(router)

    browser_capability = exports.get_capability("tool.browser.open")
    model_capability = exports.get_capability("model.completion")
    capability_ids = {capability.capability_id for capability in exports.list_capabilities()}

    assert exports.layer == "skill_hub"
    assert exports.status == "initialized"
    assert exports.capability_hub is not None
    assert browser_capability is not None
    assert model_capability is not None
    assert "tool.browser.open" in capability_ids
    assert "model.completion" in capability_ids


def test_sh_02_browser_tool_returns_standard_result_when_runtime_unavailable(monkeypatch):
    """测试项 SH-02: 浏览器 PyTool 在运行时不可用时返回统一错误结果"""
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
    assert result.output["runtime"]["playwright_installed"] is False


def test_sh_03_capability_hub_routes_tool_capability(monkeypatch):
    """测试项 SH-03: Skill Hub 统一入口可转发工具域能力"""
    monkeypatch.setattr("src.skill_hub.builtin_tools.browser_use._has_dependency", lambda name: False)
    monkeypatch.setattr("src.skill_hub.builtin_tools.browser_use._read_dependency_version", lambda name: None)
    exports = initialize()
    hub = exports.capability_hub
    register_pytools(hub, (BrowserUsePyTool(),))

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


def test_sh_04_capability_hub_routes_model_capability_to_model_domain():
    """测试项 SH-04: Skill Hub 统一入口可转发模型域能力"""

    class FakeModelProviderClient:
        provider_id = "fake"
        def completion(self, request) -> dict[str, Any]:
            assert request["model"] == "abab6.5s-chat"
            assert request["metadata"]["trace_id"] == "trace-sh-05"
            return {
                "model": "abab6.5s-chat",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "模型路由成功"},
                        "finish_reason": "stop"
                    }
                ],
                "usage": {"total_tokens": 0}
            }

    exports = initialize()
    hub = exports.capability_hub
    router = ModelRouter(clients={"default": FakeModelProviderClient()})
    hub.register_instance_capabilities(router)

    result = asyncio.run(
        exports.invoke_capability(
            CapabilityRequest(
                capability_id="model.completion",
                payload={"request": {
                    "messages": (ModelMessage(role="user", content="你好"),),
                    "model_name": "abab6.5s-chat",
                    "metadata": {"trace_id": "trace-sh-05"},
                }},
                metadata={"trace_id": "trace-sh-05"},
            )
        )
    )

    assert result.capability_id == "model.completion"
    assert result.success is True
    assert result.output["result"]["content"] == "模型路由成功"
    assert result.output["result"]["provider_id"] == "fake"
    assert result.metadata["domain"] == "model"
