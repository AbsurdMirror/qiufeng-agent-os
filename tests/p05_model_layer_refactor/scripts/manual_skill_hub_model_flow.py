#!/usr/bin/env python3
"""
P0.5 模型层重构后的手动验证脚本。

验证目标（从 skill_hub 请求入口进入）：
1. 普通文本输出（plain text）
2. 工具调用输出（tool calls）
3. 输出格式化（output_schema -> parsed）

使用方式：
- 推荐在项目根目录执行：
  python tests/p05_model_layer_refactor/scripts/manual_skill_hub_model_flow.py

环境变量（预留给 MiniMax）：
- MINIMAX_BASE_URL
- MINIMAX_API_KEY
- MINIMAX_MODEL
- USER_QUESTION
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import asdict, is_dataclass
from pprint import pprint
from typing import Any

from pydantic import BaseModel

from src.model_provider.contracts import InMemoryModelProviderClient, ModelMessage
from src.model_provider.providers.minimax import MiniMaxModelProviderClient
from src.model_provider.routing.router import ModelRouter
from src.orchestration_engine.contracts import (
    CapabilityDescription,
    CapabilityRequest,
    CapabilityResult,
)
from src.skill_hub.bootstrap import initialize as initialize_skill_hub


class FormattedAnswer(BaseModel):
    """用于验证 output_schema 解析链路。"""

    add: float
    sub: float


def _build_tools() -> tuple[CapabilityDescription, ...]:
    """构造用于工具调用验证的简单工具声明。"""
    tool_add = CapabilityDescription(
        capability_id="tool.math.add",
        domain="tool",
        name="tool_math_add",
        description="计算两个整数之和。",
        input_schema={
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        },
    )
    tool_upper = CapabilityDescription(
        capability_id="tool.text.upper",
        domain="tool",
        name="tool_text_upper",
        description="将输入文本转为大写。",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
            },
            "required": ["text"],
        },
    )
    return (tool_add, tool_upper)


def _resolve_model_client() -> tuple[ModelRouter, str]:
    """
    解析模型客户端：
    - 若提供 MiniMax 配置，则注册到 Router 并使用 MINIMAX_MODEL 作为目标 model_name；
    - 否则仅使用 default in-memory。
    """
    minimax_base_url = "https://api.minimaxi.com/v1"
    minimax_api_key = os.getenv("MINIMAX_API_KEY")
    minimax_model = "minimax/MiniMax-M2.7"

    router = ModelRouter(clients={"default": InMemoryModelProviderClient()})

    if minimax_api_key and minimax_model:
        router.add_client(
            minimax_model,
            MiniMaxModelProviderClient(
                api_key=minimax_api_key,
                model_name=minimax_model,
                base_url=minimax_base_url,
            ),
        )
        return router, minimax_model

    return router, "default"


def _build_plain_payload(model_name: str, question: str) -> dict[str, Any]:
    """普通文本场景 payload。"""
    return {
        "messages": (
            ModelMessage(role="system", content="你是一个简洁的助手。"),
            ModelMessage(role="user", content=question),
        ),
        "model_name": model_name,
    }


def _build_tool_payload(model_name: str, tools: tuple[CapabilityDescription, ...]) -> dict[str, Any]:
    """工具调用场景 payload。"""
    return {
        "messages": (
            ModelMessage(
                role="user",
                content="如果需要计算，请直接使用工具调用，不要输出自然语言解释。",
            ),
            ModelMessage(
                role="user",
                content="请计算 12 + 30，并通过工具返回。",
            ),
        ),
        "model_name": model_name,
        "tools": tools,
    }


def _build_schema_payload(model_name: str) -> dict[str, Any]:
    """输出格式化场景 payload。"""
    return {
        "messages": (
            ModelMessage(
                role="system",
                content=(
                    "给你两个数字，你需要计算它们的和与差。"
                    "不要输出其他文本。"
                ),
            ),
            ModelMessage(
                role="user",
                content=(
                    "12.3, 55.3"
                ),
            ),
        ),
        "model_name": model_name,
        "output_schema": FormattedAnswer,
        "schema_max_retries": 2,
    }


def _serialize_result(result: CapabilityResult) -> dict[str, Any]:
    """将 CapabilityResult 转成可读字典。"""
    data: dict[str, Any] = {
        "capability_id": result.capability_id,
        "success": result.success,
        "error_code": result.error_code,
        "error_message": result.error_message,
        "metadata": dict(result.metadata),
        "output": dict(result.output),
    }
    parsed = data["output"].get("parsed")
    if parsed is not None:
        if is_dataclass(parsed):
            data["output"]["parsed"] = asdict(parsed)
        elif hasattr(parsed, "model_dump"):
            data["output"]["parsed"] = parsed.model_dump()
    return data


async def _invoke_case(
    *,
    invoke_capability,
    case_name: str,
    payload: dict[str, Any],
) -> CapabilityResult:
    """执行单个测试场景并打印结果。"""
    print("\n" + "=" * 88)
    print(f"CASE: {case_name}")
    print("=" * 88)
    request = CapabilityRequest(
        capability_id="model.chat.default",
        payload=payload,
        metadata={"manual_test": "p05_model_layer_refactor"},
    )
    result = await invoke_capability(request)
    pprint(_serialize_result(result), width=120)
    return result


async def main() -> None:
    user_question = os.getenv("USER_QUESTION", "请用一句话介绍你自己。")

    model_client, model_name = _resolve_model_client()
    skill_hub = initialize_skill_hub(model_client=model_client)

    print("\n已初始化 SkillHub，模型目标:", model_name)
    print("可用能力:")
    for capability in skill_hub.list_capabilities():
        print(f"- {capability.capability_id}")

    tools = _build_tools()

    # # 场景1：普通文本
    # await _invoke_case(
    #     invoke_capability=skill_hub.invoke_capability,
    #     case_name="plain_text",
    #     payload=_build_plain_payload(model_name=model_name, question=user_question),
    # )

    # # 场景2：工具调用
    # await _invoke_case(
    #     invoke_capability=skill_hub.invoke_capability,
    #     case_name="tool_calls",
    #     payload=_build_tool_payload(model_name=model_name, tools=tools),
    # )

    # 场景3：输出格式化（schema）
    await _invoke_case(
        invoke_capability=skill_hub.invoke_capability,
        case_name="output_schema",
        payload=_build_schema_payload(model_name=model_name),
    )


if __name__ == "__main__":
    asyncio.run(main())
