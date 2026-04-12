from typing import Any, Callable, TypeVar, Type
from pydantic import BaseModel, ValidationError
import logging
import json
import re

# ============================================================
# 模型抽象层 —— Schema 强校验与自愈引擎 (Schema Validator & Auto-Healer)
#
# 本模块实现了规格 MP-P0-05（定义输出结构）、MP-P0-06（Pydantic 强校验）
# 和 MP-P0-07（基础自愈机制）。
#
# 核心问题：大语言模型（LLM）的输出是"不确定"的文本，即便你在提示词里
# 要求它输出 JSON，它也可能：
#   1. 把 JSON 包裹在 markdown 代码块里（```json ... ```）
#   2. 输出不合法的 JSON（缺逗号、多引号）
#   3. JSON 合法但字段名拼错，不符合你定义的 Schema
#
# 本模块的职责：
#   拿到 LLM 的原始输出字符串 → 尝试解析 → 用 Pydantic 验证 Schema →
#   失败时调用"自愈函数"让 LLM 重试 → 超出重试限制时抛出异常，终止流程。
#
# 使用方：应由模型层的输出转换器（Output Transformer）在拿到 LLM 原始响应后调用。
# 注意：当前本模块未被任何主调用链引入（详见整体审阅报告 REV-T5-CON-002）。
# ============================================================

logger = logging.getLogger(__name__)

# TypeVar 约束：T 必须是 Pydantic BaseModel 的子类，保证函数返回值的强类型推断
T = TypeVar("T", bound=BaseModel)


class SchemaValidationError(Exception):
    """
    Schema 校验失败异常。

    触发场景：当 JSON 解析或 Pydantic 校验失败，且调用方没有提供自愈函数时抛出。
    与 AutoHealingMaxRetriesExceeded 的区别：
        - 本类：无自愈能力（healing_func=None），直接放弃。
        - AutoHealingMaxRetriesExceeded：有自愈能力但已耗尽所有重试机会。
    """
    pass


class AutoHealingMaxRetriesExceeded(Exception):
    """
    自愈重试次数耗尽异常。

    触发场景：提供了 healing_func，但经过 max_retries 次尝试后
    仍然无法生成合法的 Schema，最终放弃并抛出此异常。
    调用方应捕获此异常，记录错误日志并向用户返回降级提示。
    """
    pass


def validate_and_heal(
    schema: Type[T],
    json_string: str,
    healing_func: Callable[[str, str], str] | None = None,
    max_retries: int = 3
) -> T:
    """
    基于 Pydantic 的强校验与自愈引擎 (MP-P0-05, MP-P0-06, MP-P0-07)。

    执行流程（每次循环为一次尝试）：
        1. 预处理：剥离 LLM 常见的 markdown 代码块包裹（```json ... ```）
        2. JSON 解析：将字符串解析为 Python dict（json.loads）
        3. Schema 校验：用 Pydantic 验证 dict 是否符合目标数据结构（model_validate）
        4. 若上述任一步骤失败：
           - 有 healing_func → 调用自愈函数获取新字符串，进入下一次循环
           - 无 healing_func → 立即抛出 SchemaValidationError（不重试）
        5. 重试次数达到 max_retries → 抛出 AutoHealingMaxRetriesExceeded

    Args:
        schema (Type[T]): Pydantic BaseModel 子类，定义期望的输出结构。
        json_string (str): LLM 返回的原始字符串，通常是 response.content 字段。
        healing_func (Callable[[str, str], str] | None): 自愈函数。
            接收两个参数：(当前错误输入, 错误信息字符串)，返回修复后的新字符串。
            通常的实现是：把错误信息连同原始输入重新发给 LLM，让它重新生成。
            若为 None，则一旦校验失败立即抛出异常，不进行任何重试。
        max_retries (int): 最大额外重试次数。默认为 3（即总共尝试 4 次）。
            注意：每次调用 healing_func 会消耗一次 LLM Token，成本需控制。

    Returns:
        T: 校验成功后的 Pydantic Model 实例，类型与 schema 参数一致。

    Raises:
        SchemaValidationError: 校验失败且 healing_func=None 时抛出。
        AutoHealingMaxRetriesExceeded: 有自愈函数但重试耗尽时抛出。

    风险提示：
        markdown 剥离逻辑使用 str.strip("`") 按字符剥离，
        存在边界 bug（详见审阅报告 [REV-MP050607-BUG-001]）。
    """
    # current_input 是当前正在处理的字符串，初始为 LLM 的原始输出
    # 每次自愈后，healing_func 的返回值会替换它，进入下一轮尝试
    current_input = json_string
    attempts = 0  # 已尝试次数计数器
    # [修复 REV-MP050607-CON-001]
    # 使用 max_total_attempts = max_retries(额外重试次数) + 1(首次执行)
    # 消除调用方对 max_retries 参数传入数值的歧义，符合人类直觉。
    max_total_attempts = max_retries + 1  

    while attempts < max_total_attempts:
        try:
            # --- 步骤 1: 预处理 —— 剥离 LLM 常见的 markdown 代码块包裹 ---
            # 问题背景：部分 LLM 会把 JSON 包在 ```json ... ``` 里，导致 json.loads 失败
            # [修复 REV-MP050607-BUG-001]
            # 弃用 str.strip('`')，改为正则表达式精确匹配前后缀，保护了 JSON 数据体内合法自带的反引号。
            current_input = re.sub(r'^```(?:json)?\s*\n?', '', current_input, flags=re.IGNORECASE)
            current_input = re.sub(r'\n?```\s*$', '', current_input).strip()

            # --- 步骤 2: JSON 解析 —— 将字符串转为 Python dict ---
            parsed_dict = json.loads(current_input)

            # --- 步骤 3: Schema 校验 —— 用 Pydantic 验证字段类型和结构 ---
            # model_validate 会对每个字段做类型检查，不符合则抛出 ValidationError
            return schema.model_validate(parsed_dict)

        except (json.JSONDecodeError, ValidationError) as e:
            # 解析或校验失败：计数 +1 并决定是否继续重试
            attempts += 1
            logger.warning(f"Schema validation failed on attempt {attempts}: {e}")

            # 已达到最大尝试次数，放弃并上报
            if attempts >= max_total_attempts:
                raise AutoHealingMaxRetriesExceeded(f"Failed to validate schema after {max_retries} retries.") from e

            if healing_func:
                # 有自愈函数：把当前错误输入和错误信息交给自愈函数，获取修复后的新字符串
                # 典型实现：healing_func 会把错误信息拼进提示词，重新请求 LLM 生成
                logger.info("Attempting auto-healing via healing_func...")
                # [修复 REV-MP050607-BUG-002]
                # 建立防护隔舱：使用 try-except 包裹第三方自愈请求（常为网络请求），
                # 防止由于自愈引擎本身崩溃抛出乱七八糟的异常给外层，破坏大逻辑兜底。
                try:
                    current_input = healing_func(current_input, str(e))
                except Exception as heal_err:
                    import traceback
                    error_details = traceback.format_exc()
                    logger.warning(
                        f"[Schema Validator] Healing attempt {attempts} failed due to unhandled exception: {heal_err}\n"
                        f"Traceback:\n{error_details}"
                    )
                    
                    # 快速失败机制 (T5 审阅 P0)
                    # 如果遇到认证失败、配置错误等致命异常，继续重试毫无意义，直接向上抛出
                    err_str = str(heal_err).lower()
                    if any(keyword in err_str for keyword in ["authentication", "auth", "api key", "quota", "billing", "unauthorized"]):
                        logger.error("[Schema Validator] Fatal error detected (auth/billing). Aborting auto-healing.")
                        raise heal_err
                        
                    raise AutoHealingMaxRetriesExceeded(
                        f"Healing function raised an exception after {attempts} attempts."
                    ) from heal_err
            else:
                # 无自愈函数：无法重试，直接抛出告知调用方，由上层决定如何降级处理
                # 如果没有提供 healing_func，简单的自愈只能是尝试截取有效部分，这里暂时抛出异常或仅依赖 Pydantic 宽容度
                raise SchemaValidationError(f"Validation failed and no healing function provided: {e}")

