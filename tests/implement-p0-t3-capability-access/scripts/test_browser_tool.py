#!/usr/bin/env python3
"""
T3 阶段：浏览器工具独立调用测试脚本

该脚本验证 Capability Hub 能够独立调用并路由到浏览器工具。
"""

import asyncio
import os
import sys
import json

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.app.bootstrap import build_application
from src.app.config import load_config
from src.domain.capabilities import CapabilityRequest


def _screenshot_dir() -> str:
    return os.path.join(
        project_root,
        "tests/implement-p0-t3-capability-access/artifacts/browser_playwright",
    )


def _assert_file_exists(path: str) -> tuple[bool, int]:
    try:
        stat = os.stat(path)
        return True, int(stat.st_size)
    except OSError:
        return False, 0

async def test_browser_tool_invocation():
    print("=" * 60)
    print("正在测试浏览器工具 (Browser PyTool) 的独立调用...")
    print("=" * 60)

    config = load_config()
    app = build_application(config)
    capability_hub = app.modules.orchestration_engine.capability_hub

    url = "https://example.com/"
    screenshot_dir = _screenshot_dir()

    req_probe = CapabilityRequest(
        capability_id="tool.browser.open",
        payload={"url": url, "probe_only": True},
        metadata={},
    )
    print(f"[步骤1] probe_only 探测依赖：{req_probe.capability_id} url={url}")
    res_probe = await capability_hub.invoke(req_probe)
    print("-" * 40)
    print(json.dumps(res_probe.output, indent=2, ensure_ascii=False))
    if not res_probe.success:
        print(f"[步骤1] 探测失败: {res_probe.error_code} {res_probe.error_message}")
        print("-" * 40)
        print("测试完成。")
        return

    req_real = CapabilityRequest(
        capability_id="tool.browser.open",
        payload={
            "url": url,
            "probe_only": False,
            "headless": True,
            "click_selector": "a",
            "wait_ms": 1000,
            "screenshot_dir": screenshot_dir,
        },
        metadata={},
    )
    print(f"[步骤2] 真实打开+点击+截图：{req_real.capability_id} url={url}")
    res_real = await capability_hub.invoke(req_real)
    print("-" * 40)
    print(json.dumps(res_real.output, indent=2, ensure_ascii=False))
    if not res_real.success:
        print(f"[步骤2] 执行失败: {res_real.error_code} {res_real.error_message}")
        print("-" * 40)
        print("测试完成。")
        return

    screenshot_path = str(res_real.output.get("screenshot_path", ""))
    exists, size = _assert_file_exists(screenshot_path) if screenshot_path else (False, 0)
    print(
        "[步骤2] 证据校验: "
        f"url_before={res_real.output.get('url_before')} "
        f"url_after={res_real.output.get('url_after')} "
        f"title_before={res_real.output.get('title_before')} "
        f"title_after={res_real.output.get('title_after')} "
        f"screenshot_exists={exists} "
        f"screenshot_size_bytes={size}"
    )

    print("-" * 40)
    print("测试完成。")

if __name__ == "__main__":
    asyncio.run(test_browser_tool_invocation())
