from collections.abc import Callable, Awaitable
from typing import Any
import functools
from src.orchestration_engine.contracts import CapabilityRequest, CapabilityResult

class SecurityError(Exception):
    pass

class ToolSecurityPrimitive:
    """
    (SH-P0-01) PyTools 安全原语实现。

    设计意图：
    提供装饰器和上下文管理器，用于限制工具执行时的资源访问。
    当前实现是一个基础拦截器，可根据工具的 ID 或 metadata 动态拦截未授权调用。
    """
    def __init__(self, allowed_domains: set[str] | None = None):
        self.allowed_domains = allowed_domains or set()

    def enforce_policy(self, request: CapabilityRequest) -> None:
        """检查能力请求是否符合安全策略"""
        # P0阶段简单的策略：检查请求中如果包含危险 metadata 标志则拒绝
        if request.metadata.get("unsafe") is True:
            raise SecurityError(f"Capability '{request.capability_id}' execution denied due to 'unsafe' metadata flag.")

        # 可进一步检查特定工具ID或文件路径权限

def with_security_policy(policy: ToolSecurityPrimitive) -> Callable:
    """
    安全策略装饰器。
    包裹 Capability handler 拦截非法调用。
    """
    def decorator(handler: Callable[[CapabilityRequest], Awaitable[CapabilityResult]]) -> Callable[[CapabilityRequest], Awaitable[CapabilityResult]]:
        @functools.wraps(handler)
        async def wrapper(request: CapabilityRequest) -> CapabilityResult:
            try:
                policy.enforce_policy(request)
            except SecurityError as e:
                return CapabilityResult(
                    capability_id=request.capability_id,
                    success=False,
                    output={},
                    error_code="security_policy_violation",
                    error_message=str(e),
                    metadata={"security_blocked": True}
                )
            # 安全检查通过后，调用原函数
            return await handler(request)
        return wrapper
    return decorator

# 提供一个全局默认策略
default_security_policy = ToolSecurityPrimitive()
