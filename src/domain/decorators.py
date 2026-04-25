from typing import Any, Callable, TypeVar
from src.domain.translators.schema_translator import SchemaTranslator
from src.domain.capabilities import CapabilityDescription

F = TypeVar("F", bound=Callable[..., Any])

def qfaos_pytool(id: str, domain: str = "tool") -> Callable[[F], F]:
    """
    [Domain Decorator] 标记函数为一个特定能力 (Capability)。
    
    设计意图：
    解耦具体业务逻辑与编排引擎。被此装饰器标记的函数在被 `SkillHub` 扫描时,
    会自动推导出对应的 `CapabilityDescription`。
    """
    def decorator(func: F) -> F:
        desc = SchemaTranslator.func_to_capability_description(func, id, domain)
        # 将描述对象附加到函数上，供 Hub 扫描识别
        setattr(func, "__qfa_capability__", desc)
        return func
    
    return decorator
