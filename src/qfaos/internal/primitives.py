import inspect
from contextvars import ContextVar, Token
from collections.abc import Callable
from typing import Any, Annotated, Tuple, Union

from pydantic import validate_call, Field

from src.skill_hub.primitives.security import (
    PolicyDecision,
    SecurityApprovalRequiredError,
    SecurityError,
    create_secure_action,
)

from ..enums import QFAEnum
from ..errors import (
    QFAInvalidConfigError,
    QFASecurityApprovalRequiredError,
    QFASecurityDeniedError,
)
from ..registry.primitive_registry import PrimitiveRegistry

_approved_ticket_id_ctx: ContextVar[str | None] = ContextVar(
    "qfaos_approved_ticket_id",
    default=None,
)


def set_approved_ticket_id(ticket_id: str | None) -> Token[str | None]:
    """为当前调用链临时注入审批票据。"""
    return _approved_ticket_id_ctx.set(ticket_id)


def reset_approved_ticket_id(token: Token[str | None]) -> None:
    """恢复票据上下文，避免污染后续调用。"""
    _approved_ticket_id_ctx.reset(token)


@validate_call
def _map_policy_value(value: Any) -> PolicyDecision:
    """
    将 SDK 枚举值映射为底层安全原语的决策枚举。
    """
    if value == QFAEnum.Primitive.Policy.Allow:
        return PolicyDecision.ALLOW
    if value == QFAEnum.Primitive.Policy.Deny:
        return PolicyDecision.DENY
    if value == QFAEnum.Primitive.Policy.AskTicket:
        return PolicyDecision.REQUIRE_TICKET
    raise QFAInvalidConfigError("安全策略必须返回 QFAEnum.Primitive.Policy 类型的值")


@validate_call
def _map_policy_result(policy_result: Any) -> Union[PolicyDecision, Tuple[PolicyDecision, Union[str, None]]]:
    """
    映射策略函数的返回值，支持单值或 (决策, 消息) 元组。
    """
    if isinstance(policy_result, tuple):
        if len(policy_result) != 2:
            raise QFAInvalidConfigError("策略元组结果必须为 (decision, message) 格式")
        decision = _map_policy_value(policy_result[0])
        message = policy_result[1]
        return decision, message
    return _map_policy_value(policy_result)


@validate_call(config={"arbitrary_types_allowed": True})
def build_secure_primitive(
    action: Annotated[Callable[..., Any], Field(description="动作函数")],
    policy: Annotated[Callable[..., Any], Field(description="策略函数")],
) -> Callable[..., Any]:
    """
    构建一个受安全策略保护的原语执行函数。
    
    该函数会自动处理策略映射、异步调用适配以及异常转换。
    """
    def _invoke_policy(*args: Any, **kwargs: Any) -> Any:
        try:
            return policy(*args, **kwargs)
        except TypeError:
            # 允许 policy 与 action 的参数名不同，按位置顺序回退调用
            return policy(*list(kwargs.values()))

    if inspect.iscoroutinefunction(policy):
        async def mapped_policy(*args: Any, **kwargs: Any) -> PolicyDecision | tuple[PolicyDecision, str | None]:
            raw = _invoke_policy(*args, **kwargs)
            if inspect.isawaitable(raw):
                raw = await raw
            return _map_policy_result(raw)
    else:
        def mapped_policy(*args: Any, **kwargs: Any) -> PolicyDecision | tuple[PolicyDecision, str | None]:
            raw = _invoke_policy(*args, **kwargs)
            return _map_policy_result(raw)

    secure_action = create_secure_action(action, mapped_policy)

    if inspect.iscoroutinefunction(secure_action):
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return await secure_action(*args, **kwargs)
            except SecurityApprovalRequiredError as exc:
                raise QFASecurityApprovalRequiredError(exc.ticket_id, str(exc)) from exc
            except SecurityError as exc:
                raise QFASecurityDeniedError(str(exc)) from exc
    else:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return secure_action(*args, **kwargs)
            except SecurityApprovalRequiredError as exc:
                raise QFASecurityApprovalRequiredError(exc.ticket_id, str(exc)) from exc
            except SecurityError as exc:
                raise QFASecurityDeniedError(str(exc)) from exc

    return wrapped


class PrimitiveAccessor:
    """
    安全原语访问器。
    
    允许用户通过 `agent.primitives.<id>(...)` 的方式便捷调用已注册的原语。
    """

    def __init__(self, registry: PrimitiveRegistry) -> None:
        """
        初始化访问器。
        
        Args:
            registry: 存储原语的注册表实例。
        """
        self._registry = registry

    def __getattr__(self, item: str) -> Callable[..., Any]:
        """
        动态获取并调用原语。
        """
        primitive = self._registry.get(item)
        if primitive is None:
            raise AttributeError(f"未注册的安全原语: '{item}'")

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            approved_ticket_id = _approved_ticket_id_ctx.get()
            if approved_ticket_id and "approved_ticket_id" not in kwargs:
                kwargs["approved_ticket_id"] = approved_ticket_id
            return primitive(*args, **kwargs)

        return _wrapped
