from typing import Callable, Annotated, Dict, Tuple

from pydantic import validate_call, Field

class PrimitiveRegistry:
    """
    安全原语注册表，用于管理所有已注册的业务安全原语。
    """

    def __init__(self) -> None:
        """
        初始化注册表。
        """
        self._primitives: Dict[str, Callable[..., object]] = {}

    @validate_call
    def register(
        self, 
        primitive_id: Annotated[str, Field(description="安全原语的唯一标识符")], 
        primitive: Annotated[Callable[..., object], Field(description="封装了安全策略的原语函数")]
    ) -> None:
        """
        在注册表中记录或覆盖一个安全原语。
        
        Args:
            primitive_id: 原语 ID。
            primitive: 原语执行函数。
        """
        self._primitives[primitive_id] = primitive

    @validate_call
    def get(
        self, 
        primitive_id: Annotated[str, Field(description="安全原语的唯一标识符")]
    ) -> Callable[..., object] | None:
        """
        根据 ID 获取对应的安全原语。
        
        Args:
            primitive_id: 原语 ID。
            
        Returns:
            Callable[..., object] | None: 已注册的原语函数，若未注册则返回 None。
        """
        return self._primitives.get(primitive_id)

    def list_primitives(self) -> Tuple[str, ...]:
        """
        获取当前已注册的所有安全原语 ID 列表。
        
        Returns:
            Tuple[str, ...]: 已注册原语 ID 的元组。
        """
        return tuple(self._primitives.keys())
