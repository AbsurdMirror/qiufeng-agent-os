#!/usr/bin/env python3
"""
T3 阶段：浏览器工具验证脚本（百度搜索 deepseek 并进入官网）
"""

import asyncio
import os
import sys
from urllib.parse import urlparse

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.app.bootstrap import build_application
from src.app.config import load_config
from src.orchestration_engine.contracts import CapabilityRequest


def _artifact_dir() -> str:
    return os.path.join(
        project_root,
        "tests/implement-p0-t3-capability-access/artifacts/browser_playwright",
    )


def _file_exists(path: str) -> tuple[bool, int]:
    try:
        stat = os.stat(path)
        return True, int(stat.st_size)
    except OSError:
        return False, 0


def _is_deepseek_official(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    return host == "deepseek.com" or host.endswith(".deepseek.com")


def _pick_deepseek_link(links: list[dict[str, str]]) -> str:
    for item in links:
        href = item.get("href")
        if isinstance(href, str) and _is_deepseek_official(href):
            return href
    return ""


async def main() -> int:
    print("=" * 60)
    print("测试：通过 tool.browser.open 访问百度搜索 deepseek，并进入 deepseek 官网")
    print("=" * 60)

    os.makedirs(_artifact_dir(), exist_ok=True)

    app = build_application(load_config())
    hub = app.modules.orchestration_engine.capability_hub

    screenshot_dir = _artifact_dir()

    search_urls = [
        "https://www.baidu.com/s?wd=deepseek%20%E5%AE%98%E7%BD%91",
        "https://www.baidu.com/s?wd=deepseek%20deepseek.com",
        "https://www.baidu.com/s?wd=DeepSeek%20%E5%AE%98%E7%BD%91",
    ]
    click_selectors = [
        "a[href*=\"deepseek.com\"]",
        "text=DeepSeek",
        "a:has-text(\"DeepSeek\")",
        "a",
    ]

    print("\n[步骤1] 百度搜索结果页尝试：goto(搜索页) -> click(候选 selector) -> wait -> screenshot，并抽取 links/page_text")
    last_error: tuple[str, str] | None = None
    last_out: dict[str, object] | None = None
    for search_url in search_urls:
        req_extract = CapabilityRequest(
            capability_id="tool.browser.open",
            payload={
                "url": search_url,
                "probe_only": False,
                "headless": True,
                "actions": [
                    {"type": "goto", "url": search_url},
                    {"type": "wait", "wait_ms": 1200},
                    {"type": "screenshot"},
                ],
                "screenshot_dir": screenshot_dir,
                "extract_text": True,
                "max_text_chars": 8000,
                "extract_links": True,
                "max_links": 80,
                "extract_dom": False,
            },
            metadata={},
        )
        print(f"\n[尝试-仅抽取链接] search_url={search_url}")
        res_extract = await hub.invoke(req_extract)
        out_extract = dict(res_extract.output)
        screenshot_path = str(out_extract.get("screenshot_path", ""))
        exists, size = _file_exists(screenshot_path) if screenshot_path else (False, 0)
        print(
            f"[证据-抽取] success={res_extract.success} "
            f"blocked_by_captcha={out_extract.get('blocked_by_captcha')} "
            f"block_reason={out_extract.get('block_reason')} "
            f"title={out_extract.get('title_after')} "
            f"url_after={out_extract.get('url_after')} "
            f"screenshot_exists={exists} size_bytes={size} "
            f"screenshot_path={screenshot_path}"
        )

        if out_extract.get("blocked_by_captcha") is True:
            print("[失败] 已被百度安全验证拦截（blocked_by_captcha=true），无法继续自动化。")
            return 1

        links = out_extract.get("links")
        if not isinstance(links, list):
            links = []
        deepseek_href = _pick_deepseek_link(links)  # type: ignore[arg-type]
        if deepseek_href:
            req_open = CapabilityRequest(
                capability_id="tool.browser.open",
                payload={
                    "url": deepseek_href,
                    "probe_only": False,
                    "headless": True,
                    "actions": [
                        {"type": "goto", "url": deepseek_href},
                        {"type": "wait", "wait_ms": 1500},
                        {"type": "screenshot"},
                    ],
                    "screenshot_dir": screenshot_dir,
                    "extract_text": True,
                    "max_text_chars": 8000,
                    "extract_links": True,
                    "max_links": 30,
                    "extract_dom": False,
                },
                metadata={},
            )
            print(f"[步骤2] 直接打开抽取到的 deepseek.com 链接：{deepseek_href}")
            res_open = await hub.invoke(req_open)
            out_open = dict(res_open.output)
            screenshot_path_2 = str(out_open.get("screenshot_path", ""))
            exists_2, size_2 = _file_exists(screenshot_path_2) if screenshot_path_2 else (False, 0)
            print(
                f"[证据-官网页] success={res_open.success} "
                f"title={out_open.get('title_after')} "
                f"url_after={out_open.get('url_after')} "
                f"screenshot_exists={exists_2} size_bytes={size_2} "
                f"screenshot_path={screenshot_path_2}"
            )
            if res_open.success and isinstance(out_open.get("url_after"), str) and _is_deepseek_official(out_open["url_after"]):  # type: ignore[index]
                print("[判定] 已进入 deepseek 官网（url_after 命中 deepseek.com）。")
                return 0

        for selector in click_selectors:
            req = CapabilityRequest(
                capability_id="tool.browser.open",
                payload={
                    "url": search_url,
                    "probe_only": False,
                    "headless": True,
                    "actions": [
                        {"type": "goto", "url": search_url},
                        {"type": "wait", "wait_ms": 800},
                        {"type": "click", "selector": selector},
                        {"type": "wait", "wait_ms": 1200},
                        {"type": "screenshot"},
                    ],
                    "screenshot_dir": screenshot_dir,
                    "extract_text": True,
                    "max_text_chars": 8000,
                    "extract_links": True,
                    "max_links": 50,
                    "extract_dom": False,
                },
                metadata={},
            )
            print(f"\n[尝试] search_url={search_url} click_selector={selector}")
            res = await hub.invoke(req)
            out = dict(res.output)
            screenshot_path = str(out.get("screenshot_path", ""))
            exists, size = _file_exists(screenshot_path) if screenshot_path else (False, 0)
            print(
                f"[证据] success={res.success} "
                f"blocked_by_captcha={out.get('blocked_by_captcha')} "
                f"block_reason={out.get('block_reason')} "
                f"title={out.get('title_after')} "
                f"url_after={out.get('url_after')} "
                f"screenshot_exists={exists} size_bytes={size} "
                f"screenshot_path={screenshot_path}"
            )

            if out.get("blocked_by_captcha") is True:
                print("[失败] 已被百度安全验证拦截（blocked_by_captcha=true），无法继续自动化。")
                return 1

            url_after = out.get("url_after")
            if res.success and isinstance(url_after, str) and _is_deepseek_official(url_after):
                print("[判定] 已进入 deepseek 官网（url_after 命中 deepseek.com）。")
                return 0

            last_error = (res.error_code or "unknown", res.error_message or "")
            last_out = out

    print("\n[最终失败] 未能稳定从百度搜索跳转到 deepseek 官网（deepseek.com）。")
    if last_error is not None:
        print(f"[最后一次错误] {last_error[0]}: {last_error[1]}")
    if last_out is not None:
        links = last_out.get("links")
        if isinstance(links, list):
            top_links = []
            for item in links[:10]:
                if isinstance(item, dict):
                    top_links.append({"href": item.get("href", ""), "text": item.get("text", "")})
            print(f"[最后一次抽取到的前10条链接] {top_links}")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
