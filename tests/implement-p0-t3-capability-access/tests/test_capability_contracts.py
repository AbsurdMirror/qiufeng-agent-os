import asyncio

from src.orchestration_engine import initialize
from src.domain.capabilities import CapabilityDescription, CapabilityRequest
from src.orchestration_engine.contracts import NullCapabilityHub


def test_oe_08_null_capability_hub_supports_discovery():
    """测试项 OE-08: 空能力中心支持统一能力发现协议"""
    description = CapabilityDescription(
        capability_id="tool.browser.open",
        domain="tool",
        name="browser_open",
        description="打开浏览器页面",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )
    hub = NullCapabilityHub(capabilities=(description,))

    assert hub.list_capabilities() == (description,)
    assert hub.get_capability("tool.browser.open") == description


def test_oe_09_null_capability_hub_returns_standard_result():
    """测试项 OE-09: 空能力中心返回统一错误结果结构"""
    hub = NullCapabilityHub()
    result = asyncio.run(
        hub.invoke(CapabilityRequest(capability_id="model.chat.default"))
    )

    assert result.capability_id == "model.chat.default"
    assert result.success is False
    assert result.error_code == "capability_not_found"
    assert result.output == {}


def test_oe_10_initialize_exposes_typed_capability_exports():
    """测试项 OE-10: 编排层导出对齐强类型 Capability 接口"""
    exports = initialize()

    assert exports.list_capabilities() == ()
    assert exports.get_capability("tool.browser.open") is None

    result = asyncio.run(
        exports.invoke_capability(
            CapabilityRequest(capability_id="tool.browser.open")
        )
    )
    assert result.success is False
    assert result.error_code == "capability_not_found"


def test_oe_11_initialize_supports_injected_capability_hub():
    """测试项 OE-11: 编排层初始化支持挂载外部 Capability Hub"""
    description = CapabilityDescription(
        capability_id="tool.browser.open",
        domain="tool",
        name="browser_open",
        description="打开浏览器页面",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )
    hub = NullCapabilityHub(capabilities=(description,))

    exports = initialize(capability_hub=hub)

    assert exports.capability_hub is hub
    assert exports.list_capabilities() == (description,)
    assert exports.get_capability("tool.browser.open") == description
