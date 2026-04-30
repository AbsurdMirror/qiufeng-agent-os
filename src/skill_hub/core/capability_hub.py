from asyncio import to_thread
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, Annotated
import inspect

from pydantic import Field
from src.domain.capabilities import CapabilityDescription, CapabilityRequest, CapabilityResult
from src.domain.translators.schema_translator import SchemaTranslator
from src.domain.models import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)
from src.domain.errors import format_user_facing_error
from src.model_provider.contracts import ModelProviderClient
from src.skill_hub.contracts import PyTool
from src.skill_hub.primitives.security import with_security_policy, default_security_policy
from src.observability_hub.exports import ObservabilityHubExports

# ============================================================
# 能力中心 —— 注册中心与调度总线 (Capability Hub)
#
# 本模块是整个 Agent-OS 的"总机"。所有供大模型使用的工具、甚至模型自身发起的
# 对话请求，都被抽象为统一的「能力 (Capability)」，并注册到 RegisteredCapabilityHub。
#
# T5 架构升级 (SH-P0-01)：
#   在 `register_capability` 时，统一注入了安全管控拦截器 `with_security_policy`。
#   这保证了所有的调用（无论是内置工具还是外部扩展）都会强制经过安全原语的审计。
# ============================================================


CapabilityHandler = Callable[[CapabilityRequest], Awaitable[CapabilityResult]]


class RegisteredCapabilityHub:
    """
    编排层可见的统一能力注册中心。
    
    设计意图：
    实现 `CapabilityHub` 协议，提供能力的注册、发现和调用。
    所有的工具（PyTool）和模型路由都会注册到这里，编排层只需要通过唯一的 `invoke` 方法
    和能力 ID，就能调用底层的任何功能。这也为拦截器（审计、日志、安全验证）提供了单一挂载点。
    """
    def __init__(self, observability: ObservabilityHubExports | None = None) -> None:
        self._capabilities: dict[str, CapabilityDescription] = {}
        self._handlers: dict[str, CapabilityHandler] = {}
        self._observability = observability

    def register_capability(
        self,
        capability: CapabilityDescription,
        handler: CapabilityHandler,
    ) -> CapabilityDescription:
        """
        注册一个能力及其对应的异步处理函数。
        
        T5 新增：针对工具类型的能力，自动使用 default_security_policy 包装，
        拦截越权或非法的资源访问。模型能力不应用该沙盒以避免网络误伤。
        """
        self._capabilities[capability.capability_id] = capability
        # 仅针对 tool 域（即 PyTools）应用安全原语拦截，不对 model 等路由施加沙盒
        # [业务设计补充]：
        # 如果一刀切地把大模型的纯对话网络请求（domain="model"）也框进这个底层安全沙盒，
        # 因为沙盒默认拦截未知路径，会导致大模型彻底变成“聋子和哑巴”（甚至无法请求 OpenAI/MiniMax 接口）。
        # 因此必须进行域隔离，特权网络请求放行，只约束落地执行阶段的危险动作。
        if capability.domain == "tool":
            safe_handler = with_security_policy(default_security_policy)(handler)
        else:
            safe_handler = handler
        self._handlers[capability.capability_id] = safe_handler
        return capability

    def register_instance_capabilities(self, instance: Any) -> list[CapabilityDescription]:
        """
        自动扫描并注册类实例中被 @qfaos_pytool 装饰的方法。
        
        设计意图：
        支持类级别的能力定义，自动处理参数校验与结果转换。
        """
        registered = []
        # 获取所有成员方法
        for name, method in inspect.getmembers(instance, predicate=inspect.ismethod):
            # 装饰器打上的元数据标签
            meta_desc = getattr(method, "__qfa_capability__", None)
            if not isinstance(meta_desc, CapabilityDescription):
                continue
            
            # 构造自动处理的 Handler
            async def auto_handler(request: CapabilityRequest, _method=method, _desc=meta_desc) -> CapabilityResult:
                # 1. 验证并转换输入载荷 (聚合参数)
                params_obj = SchemaTranslator.validate_payload(_desc.input_model, request.payload or {})
                
                # 提取参数字典
                params = dict(params_obj)
                
                # 自动合并：将 CapabilityRequest.metadata 合并到方法的 metadata 参数中（如果存在）
                if "metadata" in params and isinstance(params["metadata"], dict):
                    merged_meta = dict(request.metadata)
                    merged_meta.update(params["metadata"])
                    params["metadata"] = merged_meta
                
                # 2. 执行方法 (支持异步/同步)
                result = _method(**params)
                if inspect.isawaitable(result):
                    result = await result
                
                # 3. 验证并转换返回值 (归一化为 dict)
                output = SchemaTranslator.serialize_instance(_desc.output_model, result)
                
                return CapabilityResult(
                    capability_id=request.capability_id,
                    success=True,
                    output=output,
                )

            self.register_capability(meta_desc, auto_handler)
            registered.append(meta_desc)
        return registered

    def list_capabilities(self) -> tuple[CapabilityDescription, ...]:
        return tuple(self._capabilities.values())

    def get_capability(self, capability_id: str) -> CapabilityDescription | None:
        return self._capabilities.get(capability_id)

    async def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        """
        统一的调用入口。
        所有编排层的能力调用都将通过此方法分发。
        """
        capability = self.get_capability(request.capability_id)
        if capability is None:
            return CapabilityResult(
                capability_id=request.capability_id,
                success=False,
                output={},
                error_code="capability_not_found",
                error_message=f"capability '{request.capability_id}' is not registered",
            )
        handler = self._handlers[request.capability_id]
        
        trace_id = request.metadata.get("trace_id", "unknown")
        if self._observability:
            self._observability.record(
                trace_id,
                {
                    "event": "capability.invoke.started",
                    "capability_id": request.capability_id,
                    "payload": request.payload,
                    "domain": capability.domain,
                },
                "INFO",
            )

        # 异常隔离兜底：如果 handler 内部由于（如模型超时、JSON 解析失败等）抛出未捕获异常，
        # 在此处被捕获并转化为 CapabilityResult(success=False)，防止整个编排主协程崩溃。
        try:
            result = await handler(request)
        except Exception as e:
            error = format_user_facing_error(e, summary="能力调用失败")
            print(error)
            if self._observability:
                self._observability.record(
                    trace_id,
                    {
                        "event": "capability.invoke.failed",
                        "capability_id": request.capability_id,
                        "error": error,
                    },
                    "ERROR",
                )
            return CapabilityResult(
                capability_id=request.capability_id,
                success=False,
                output={},
                error_code="capability_execution_failed",
                error_message=error,
                metadata={"domain": capability.domain}
            )
        
        if self._observability:
            self._observability.record(
                trace_id,
                {
                    "event": "capability.invoke.completed",
                    "capability_id": result.capability_id,
                    "success": result.success,
                    "output": result.output if result.success else None,
                    "error_message": result.error_message if not result.success else None,
                },
                "INFO" if result.success else "WARNING",
            )

        metadata = dict(result.metadata)
        metadata.setdefault("domain", capability.domain)
        return CapabilityResult(
            capability_id=result.capability_id,
            success=result.success,
            output=dict(result.output),
            error_code=result.error_code,
            error_message=result.error_message,
            metadata=metadata,
        )


def register_pytools(
    hub: RegisteredCapabilityHub,
    pytools: Iterable[PyTool],
) -> None:
    for pytool in pytools:
        hub.register_capability(pytool.capability, pytool.invoke)

