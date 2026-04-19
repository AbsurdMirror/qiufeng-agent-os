#!/usr/bin/env python3
"""
P0.5 模型层重构后的手动验证脚本：ReAct 循环与 Schema 解析。

验证目标：
1. 模型能够根据问题多次调用工具（add, multiply）。
2. 我们在脚本中拦截 tool_calls，本地执行，并将结果追加到 messages。
3. 模型最终计算完毕后，按照 output_schema 输出 JSON，并被成功解析。

使用方式：
- 推荐在项目根目录执行：
  python tests/p05_model_layer_refactor/scripts/manual_react_with_schema.py

环境变量（预留给 MiniMax）：
- MINIMAX_BASE_URL
- MINIMAX_API_KEY
- MINIMAX_MODEL
"""

from __future__ import annotations

import asyncio
import json
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


class CalculationResult(BaseModel):
    """用于验证最终 output_schema 解析链路。"""
    expression: str
    result: int


def _build_tools() -> tuple[CapabilityDescription, ...]:
    """构造用于工具调用验证的工具声明。"""
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
    tool_multiply = CapabilityDescription(
        capability_id="tool.math.multiply",
        domain="tool",
        name="tool_math_multiply",
        description="计算两个整数的乘积。",
        input_schema={
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        },
    )
    return (tool_add, tool_multiply)


def _execute_tool(capability_id: str, payload: dict[str, Any]) -> Any:
    """本地模拟执行工具"""
    print(f"    [Local Execution] Running {capability_id} with {payload}")
    if capability_id == "tool.math.add":
        return payload["a"] + payload["b"]
    elif capability_id == "tool.math.multiply":
        return payload["a"] * payload["b"]
    return f"Unknown tool: {capability_id}"


def _resolve_model_client() -> tuple[ModelRouter, str]:
    """解析模型客户端"""
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


async def main() -> None:
    model_client, model_name = _resolve_model_client()
    skill_hub = initialize_skill_hub(model_client=model_client)

    print(f"已初始化 SkillHub，模型目标: {model_name}")
    tools = _build_tools()

    messages = [
        ModelMessage(
            role="system",
            content="你是一个计算助手。请先使用工具进行逐步计算，得到最终结果后，再输出 JSON 格式的最终答案。"
        ),
        ModelMessage(
            role="user",
            content="请计算 (12 + 34) * 5 的结果。"
        ),
    ]

    max_turns = 5
    for turn in range(1, max_turns + 1):
        print(f"\n========== Turn {turn} ==========")
        payload = {
            "messages": tuple(messages),
            "model_name": model_name,
            "tools": tools,
            "output_schema": CalculationResult,
            "schema_max_retries": 2,
        }
        request = CapabilityRequest(
            capability_id="model.chat.default",
            payload=payload,
            metadata={"manual_test": "react_with_schema"},
        )
        
        result = await skill_hub.invoke_capability(request)
        if not result.success:
            print("调用失败！")
            pprint(_serialize_result(result))
            break
            
        output = result.output
        tool_calls = output.get("tool_calls")
        parsed = output.get("parsed")
        content = output.get("content")
        
        print(f"  模型回复内容: {content}")
        
        if tool_calls:
            print(f"  模型决定调用工具 ({len(tool_calls)}个):")
            # 将模型的工具调用意图追加到上下文，由于 ModelMessage 限制，这里序列化为文本
            messages.append(ModelMessage(
                role="assistant",
                content=f"调用工具: {json.dumps(tool_calls, ensure_ascii=False)}"
            ))
            
            for call in tool_calls:
                cap_id = call["capability_id"]
                args = call["payload"]
                res = _execute_tool(cap_id, args)
                # 将工具执行结果追加到上下文
                messages.append(ModelMessage(
                    role="user",
                    content=f"工具 {cap_id} 返回结果: {res}"
                ))
        elif parsed:
            print("  🎉 模型输出了符合 output_schema 的结果！")
            pprint(_serialize_result(result))
            break
        else:
            print("  ⚠️ 模型既没有调用工具，也没有输出符合 schema 的结果。")
            pprint(_serialize_result(result))
            # 可能是 content 被拒绝，或者模型直接返回了纯文本
            messages.append(ModelMessage(
                role="assistant",
                content=content or ""
            ))
            messages.append(ModelMessage(
                role="user",
                content="请根据前面的计算结果，使用指定的 output_schema 格式输出最终结果。"
            ))

if __name__ == "__main__":
    asyncio.run(main())
