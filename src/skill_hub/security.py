from collections.abc import Callable, Awaitable
from typing import Any
import functools
from src.orchestration_engine.contracts import CapabilityRequest, CapabilityResult

# ============================================================
# 能力中心 —— 安全原语 (Security Primitive)
#
# 本模块实现了规格 SH-P0-01（PyTools 安全原语实现）。
#
# 设计意图：
#   在大模型调用本地工具链（尤其是文件读写、沙盒执行等）时，需要提供安全管控能力。
#   本模块提供：
#   1. ToolSecurityPrimitive: 安全策略引擎（当前为防御示例架构）
#   2. with_security_policy: 用于拦截非法调用的函数装饰器
#
# 使用方式：
#   在注册工具时，使用装饰器包装实际处理函数：
#   @with_security_policy(default_security_policy)
#   async def my_tool_handler(req: CapabilityRequest) -> CapabilityResult:
#       ...
# ============================================================


class SecurityError(Exception):
    """
    安全策略拦截异常。
    当请求未能通过 ToolSecurityPrimitive 的校验时抛出。
    """
    pass


class ToolSecurityPrimitive:
    """
    (SH-P0-01) PyTools 安全原语实现。

    当前实现是一个基础的架构桩（Stub），主要用于验证安全拦截器的工作流。
    可以在此基础上扩展出真正的资源控制逻辑（如网络白名单、文件系统 Jail 等）。

    Attributes:
        allowed_domains (set[str]): 允许访问的网络域名集合（示例字段，当前未应用）。
    """
    def __init__(self, allowed_domains: set[str] | None = None):
        # 允许访问的域名白名单。
        # 注意：P0 阶段该字段虽已定义但未在 enforce_policy 中生效。
        self.allowed_domains = allowed_domains or set()

    def enforce_policy(self, request: CapabilityRequest) -> None:
        """
        检查能力请求是否符合安全策略，不符合则抛出 SecurityError。

        执行流程：
            1. 检查请求的 metadata 中是否显式包含了 'unsafe': True 的标志。
            2. 如果是，立刻拒绝并抛出异常。
            3. 如果通过检查，函数正常返回 None。

        Args:
            request (CapabilityRequest): 待验证的工具调用请求。

        风险提示：
            当前策略仅依赖请求中调用方主动设置的 metadata（形式安全）。
            对于恶意的工具调用，无法起到真正的防御作用（参见审阅报告）。
        """
        # P0阶段简单的策略：检查请求中如果包含危险 metadata 标志则拒绝
        if request.metadata.get("unsafe") is True:
            raise SecurityError(f"Capability '{request.capability_id}' execution denied due to 'unsafe' metadata flag.")

        # TODO: 可进一步检查特定工具ID或文件路径权限
        # 例如：针对 "http_request" 工具检查 request.args["url"] 是否属于 self.allowed_domains


def with_security_policy(policy: ToolSecurityPrimitive) -> Callable:
    """
    安全策略拦截器（装饰器）。

    设计意图：
        包裹基础的 Capability handler。在正式执行 handler 逻辑前，
        调用 policy 引擎进行安全校验。如果校验失败，将 SecurityError 转化为一个
        标准化、表达失败的 CapabilityResult 返回，避免让调用方崩溃。

    Args:
        policy (ToolSecurityPrimitive): 要挂载的安全策略实例。
    """
    def decorator(handler: Callable[[CapabilityRequest], Awaitable[CapabilityResult]]) -> Callable[[CapabilityRequest], Awaitable[CapabilityResult]]:
        @functools.wraps(handler)
        async def wrapper(request: CapabilityRequest) -> CapabilityResult:
            try:
                # 首先执行安全校验
                policy.enforce_policy(request)
            except SecurityError as e:
                # 校验失败时：触发平滑降级
                # 不抛出异常，而是构造并返回一个包含明确错误码的 CapabilityResult，
                # 这样编排引擎就能正常收到结果（虽然是失败的结果），并让 LLM 知道调用被拦截了
                return CapabilityResult(
                    capability_id=request.capability_id,
                    success=False,
                    output={},
                    error_code="security_policy_violation",
                    error_message=str(e),
                    metadata={"security_blocked": True}  # 注入安全拦截标记
                )
            
            # 安全检查通过后，调用原函数执行具体业务逻辑
            return await handler(request)
        return wrapper
    return decorator


# 提供一个全局默认策略实例，供简单的全局调用或默认配置使用
default_security_policy = ToolSecurityPrimitive()

