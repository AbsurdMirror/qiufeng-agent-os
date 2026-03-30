#!/usr/bin/env python3
"""
T3 阶段：简易 Agent 手动测试脚本 (Feishu -> MiniMax -> Console)

该脚本验证从飞书接收消息并调用 MiniMax 模型的全链路。
"""

import asyncio
import multiprocessing as mp
import os
import sys
import time
import json

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.app.bootstrap import build_application
from src.app.config import load_config
from src.app.config import AppConfig
from src.channel_gateway.events import UniversalEvent, UniversalEventContent
from src.orchestration_engine.contracts import CapabilityRequest

def _extract_text_content(event: UniversalEvent) -> str:
    if isinstance(event.text, str) and event.text:
        return event.text
    texts: list[str] = []
    for content in event.contents:
        if isinstance(content, UniversalEventContent) and content.type == "text":
            texts.append(str(content.data))
    if texts:
        return " ".join(texts)
    return str(event.contents)

def _ensure_minimax_config() -> None:
    """检查并交互式配置 MiniMax 环境变量"""
    print("\n[配置检查] 正在检查 MiniMax 环境变量...")
    
    # 定义需要检查的环境变量
    configs = {
        "QF_MINIMAX_API_KEY": "请输入 MiniMax API Key (QF_MINIMAX_API_KEY): ",
        "QF_MINIMAX_MODEL": "请输入 MiniMax 模型名称 (QF_MINIMAX_MODEL, 默认 abab6.5s-chat): ",
        "QF_MINIMAX_BASE_URL": "请输入 MiniMax Base URL (QF_MINIMAX_BASE_URL, 默认 https://api.minimax.chat/v1): "
    }
    
    defaults = {
        "QF_MINIMAX_MODEL": "abab6.5s-chat",
        "QF_MINIMAX_BASE_URL": "https://api.minimax.chat/v1"
    }

    for env_var, prompt in configs.items():
        if not os.getenv(env_var):
            value = input(prompt).strip()
            if not value and env_var in defaults:
                value = defaults[env_var]
            
            if value:
                os.environ[env_var] = value
                print(f"  已设置 {env_var}")
            else:
                if env_var == "QF_MINIMAX_API_KEY":
                    print(f"  警告: {env_var} 未设置，模型调用可能会失败。")
        else:
            # 隐藏 API Key 的部分内容
            val = os.getenv(env_var)
            display_val = val[:6] + "******" if env_var == "QF_MINIMAX_API_KEY" and val else val
            print(f"  检测到 {env_var}: {display_val}")
    print("[配置检查] 完成。\n")

async def run_simple_agent_test() -> None:
    print("=" * 60)
    print("准备启动 [T3 简易 Agent] 飞书长连接进行手动测试...")
    print("流程：接收飞书消息 -> 调用 MiniMax 模型 -> 命令行打印回复")
    print("=" * 60)

    # 交互式检查配置
    _ensure_minimax_config()

    config = load_config()
    app = build_application(config)

    if app.config.feishu is None:
        print("错误: 未找到飞书配置，请先运行 config-feishu 命令")
        return

    capability_hub = app.modules.orchestration_engine.capability_hub
    
    process_context = mp.get_context("spawn")
    event_queue = process_context.Queue()
    long_connection_process = process_context.Process(
        target=_run_long_connection_process,
        args=(app.config, event_queue),
        daemon=True,
    )
    active_tasks: set[asyncio.Task[None]] = set()

    async def _handle_event(event: UniversalEvent) -> None:
        text_content = _extract_text_content(event)
        started_at = time.perf_counter()
        
        print(f"\n[收到飞书消息] User: {event.user_id} 内容: {text_content}")

        # 构造对 MiniMax 的调用请求
        req = CapabilityRequest(
            capability_id="model.minimax.chat",
            payload={"prompt": text_content},
            metadata={}
        )

        print(f"[正在调用 MiniMax 模型...]")
        
        # 统一经过 Capability Hub 调用
        result = await capability_hub.invoke(req)
        elapsed = time.perf_counter() - started_at
        
        print("-" * 40)
        if result.success:
            # 这里的 output 是 ModelResponse 的 dict 形式，内容在 content 字段
            model_output = result.output.get("content", " (空回复) ")
            provider = result.output.get("provider_id", "unknown")
            print(f"[MiniMax 回复] ({provider}):\n{model_output}")
        else:
            print(f"[调用失败] 错误码: {result.error_code}")
            print(f"[错误信息] {result.error_message}")
        
        print(f"[处理总耗时] {elapsed:.2f}s")
        print("-" * 40 + "\n")

    async def _consume_event_loop() -> None:
        while True:
            event = await asyncio.to_thread(event_queue.get)
            task = asyncio.create_task(_handle_event(event))
            active_tasks.add(task)
            task.add_done_callback(active_tasks.discard)

    async def _run_long_connection() -> None:
        long_connection_process.start()
        try:
            while long_connection_process.is_alive():
                await asyncio.sleep(1)
        finally:
            if long_connection_process.is_alive():
                long_connection_process.terminate()
                long_connection_process.join(timeout=3)

    print("服务启动中...请在飞书向机器人发送消息。")
    print("=" * 60)
    await asyncio.gather(_consume_event_loop(), _run_long_connection())

def _run_long_connection_process(config: AppConfig, event_queue: mp.Queue) -> None:
    app = build_application(config)
    gateway = app.modules.channel_gateway
    runtime = gateway.feishu_long_connection
    if not runtime.initialized:
        raise RuntimeError(runtime.error or "feishu_long_connection_unavailable")

    def _on_text_event(event: UniversalEvent) -> None:
        event_queue.put(event)

    gateway.run_feishu_long_connection(
        app.config.feishu,
        _on_text_event,
    )

if __name__ == "__main__":
    try:
        asyncio.run(run_simple_agent_test())
    except KeyboardInterrupt:
        print("\n手动测试结束。")
