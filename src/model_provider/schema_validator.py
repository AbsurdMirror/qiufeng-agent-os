from typing import Any, Callable, TypeVar, Type
from pydantic import BaseModel, ValidationError
import logging
import json

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

class SchemaValidationError(Exception):
    pass

class AutoHealingMaxRetriesExceeded(Exception):
    pass

def validate_and_heal(
    schema: Type[T],
    json_string: str,
    healing_func: Callable[[str, str], str] | None = None,
    max_retries: int = 3
) -> T:
    """
    (MP-P0-05, MP-P0-06, MP-P0-07) 基于 Pydantic 的强校验和自愈机制。

    参数:
    - schema: Pydantic BaseModel 类型，定义了模型输出结构。
    - json_string: 模型返回的 JSON 字符串（通常为 content 字段）。
    - healing_func: 基础自愈函数。接收原始输入和错误信息，尝试让模型重新生成正确格式。
    - max_retries: 最大重试次数。
    """
    current_input = json_string
    attempts = 0

    while attempts < max_retries:
        try:
            # 尝试修复一些常见的 JSON 格式错误（比如被 markdown code block 包裹）
            if current_input.startswith("```json"):
                current_input = current_input.strip("`").removeprefix("json").strip()
            elif current_input.startswith("```"):
                current_input = current_input.strip("`").strip()

            parsed_dict = json.loads(current_input)
            return schema.model_validate(parsed_dict)

        except (json.JSONDecodeError, ValidationError) as e:
            attempts += 1
            logger.warning(f"Schema validation failed on attempt {attempts}: {e}")
            if attempts >= max_retries:
                raise AutoHealingMaxRetriesExceeded(f"Failed to validate schema after {max_retries} attempts.") from e

            if healing_func:
                logger.info("Attempting auto-healing via healing_func...")
                current_input = healing_func(current_input, str(e))
            else:
                # 如果没有提供 healing_func，简单的自愈只能是尝试截取有效部分，这里暂时抛出异常或仅依赖 Pydantic 宽容度
                raise SchemaValidationError(f"Validation failed and no healing function provided: {e}")
