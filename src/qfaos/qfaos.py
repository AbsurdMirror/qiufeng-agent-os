from inspect import iscoroutinefunction
from collections.abc import Callable
from typing import Annotated, Any

from pydantic import validate_call, Field

import asyncio
import multiprocessing as mp

from src.channel_gateway.bootstrap import initialize as initialize_channel_gateway
from src.channel_gateway.channels.feishu.long_connection import run_feishu_long_connection
from src.domain.translators.schema_translator import SchemaTranslator
from src.model_provider.contracts import InMemoryModelProviderClient
from src.model_provider.providers.minimax import MiniMaxModelProviderClient
from src.model_provider.routing.router import ModelRouter
from src.observability_hub.bootstrap import initialize as initialize_observability_hub
from src.orchestration_engine.bootstrap import initialize as initialize_orchestration_engine
from src.qfaos.runtime.custom_orchestrator import CustomExecuteOrchestrator
from src.skill_hub.bootstrap import initialize as initialize_skill_hub
from src.skill_hub.builtin_tools.browser_use import BrowserUsePyTool
from src.skill_hub.core.capability_hub import register_pytools
from src.storage_memory.bootstrap import initialize as initialize_storage_memory

from .enums import QFAEnum
from .config import QFAConfig
from .registry.channel_registry import ChannelRegistry
from .registry.model_registry import ModelRegistry
from .registry.primitive_registry import PrimitiveRegistry
from .registry.tool_registry import ToolRegistry
from .registry.memory_registry import MemoryRegistry
from .registry.observability_registry import ObservabilityRegistry
from .internal.validation import validate_feishu_mode_requirements
from .internal.primitives import PrimitiveAccessor, build_secure_primitive
from .internal.tools import FunctionPyTool
from .errors import (
    QFAInvalidConfigError,
    QFAUnsupportedChannelError,
    QFAUnsupportedModelError,
)
from .runtime.contracts import QFAExecutionContext, QFAEvent

class QFAOS:
    """
    QFAOS SDK 的核心入口类。
    
    负责协调渠道（Channel）、模型（Model）、工具（Tool）及记忆（Memory）等组件的注册与运行。
    本类通过 Pydantic V2 的 @validate_call 提供运行时类型安全保障。
    """

    def __init__(self):
        """
        初始化 QFAOS 实例。
        
        创建内部组件注册表。此时不会产生网络连接或加载外部驱动。
        """
        self._channel_registry = ChannelRegistry()
        self._model_registry = ModelRegistry()
        self._primitive_registry = PrimitiveRegistry()
        self._tool_registry = ToolRegistry()
        self._memory_registry = MemoryRegistry()
        self._observability_registry = ObservabilityRegistry()
        self._primitive_accessor = PrimitiveAccessor(self._primitive_registry)
        self._execute_handler: Callable[[QFAEvent, QFAExecutionContext], Any] | None = None
        self._enable_builtin_tools: bool = False

    @validate_call
    def enable_builtin_tools(self, enable: bool = True) -> None:
        """
        [SDK] 配置是否挂载全部内置工具。
        """
        self._enable_builtin_tools = enable

    @validate_call
    def register_channel(
        self,
        channel: Annotated[QFAEnum.Channel, Field(description="渠道类型枚举")],
        config: Annotated[QFAConfig.ChannelConfigUnion, Field(description="对应的渠道配置模型")]
    ) -> None:
        """
        注册一个新的渠道配置。
        
        该接口采用 Pydantic 原生函数签名与 Annotated 元数据进行严格校验。
        
        Args:
            channel: 渠道类型，目前仅支持 QFAEnum.Channel.Feishu。
            config: 渠道对应的配置对象，必须与 channel 类型匹配。
            
        Raises:
            QFAUnsupportedChannelError: 当传入不支持的渠道类型时抛出。
            QFAInvalidConfigError: 当配置对象与渠道类型不匹配，或配置内部校验失败时抛出。
        """
        # 1. 验证渠道类型是否受支持
        if channel != QFAEnum.Channel.Feishu:
            raise QFAUnsupportedChannelError(f"目前暂不支持渠道类型: {channel}")

        # 2. 验证配置模型是否与渠道匹配
        if channel == QFAEnum.Channel.Feishu and not isinstance(config, QFAConfig.Channel.Feishu):
            raise QFAInvalidConfigError(
                f"飞书渠道需要 {QFAConfig.Channel.Feishu.__name__} 类型的配置，但收到了 {type(config).__name__}"
            )

        # 3. 执行特定渠道的业务逻辑校验（如飞书 Webhook 模式的必填项）
        validate_feishu_mode_requirements(config)
        
        # 4. 存入注册表
        self._channel_registry.register(channel, config)

    @validate_call
    def register_model(
        self,
        model: Annotated[QFAEnum.Model, Field(description="模型类型枚举")],
        config: Annotated[QFAConfig.ModelConfigUnion, Field(description="对应的模型配置模型")]
    ) -> None:
        """
        注册一个新的模型配置。
        
        Args:
            model: 模型类型（目前支持 QFAEnum.Model.MiniMax）。
            config: 模型对应的配置对象，必须与 model 类型匹配。
            
        Raises:
            QFAUnsupportedModelError: 当传入不支持的模型类型时抛出。
            QFAInvalidConfigError: 当配置对象与模型类型不匹配时抛出。
        """
        # 1. 验证模型类型是否受支持
        if model != QFAEnum.Model.MiniMax:
            raise QFAUnsupportedModelError(f"目前暂不支持模型类型: {model}")

        # 2. 验证配置模型是否与模型类型匹配
        if model == QFAEnum.Model.MiniMax and not isinstance(config, QFAConfig.Model.MiniMax):
            raise QFAInvalidConfigError(
                f"MiniMax 模型需要 {QFAConfig.Model.MiniMax.__name__} 类型的配置，但收到了 {type(config).__name__}"
            )

        # 3. 存入注册表
        self._model_registry.register(model, config)

    @validate_call
    def register_security_primitive(
        self,
        primitive_id: Annotated[str, Field(min_length=1, description="安全原语的唯一标识符")],
        action: Annotated[Callable[..., Any], Field(description="原语执行的动作函数")],
        policy: Annotated[Callable[..., Any], Field(description="决策是否允许执行动作的策略函数")],
    ) -> None:
        """
        注册一个安全原语。
        
        策略函数返回 Allow/Deny/AskTicket 来控制 action 是否执行。
        
        Args:
            primitive_id: 原语 ID，不能为空。
            action: 实际执行业务逻辑的函数。
            policy: 负责安全审计与决策的函数。
            
        Raises:
            QFAInvalidConfigError: 当 primitive_id 为空时抛出。
        """
        normalized_id = primitive_id.strip()
        if not normalized_id:
            raise QFAInvalidConfigError("安全原语 ID 不能为空")

        secure_primitive = build_secure_primitive(action, policy)
        self._primitive_registry.register(normalized_id, secure_primitive)

    @validate_call
    def pytool(
        self,
        tool_id: Annotated[str, Field(min_length=1, description="工具的唯一标识符")],
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """
        [推荐接口] 装饰即注册：将一个函数标记为工具并自动注册到 QFAOS。
        
        该装饰器集成了元数据推导、运行时校验与自动化注册，是定义自定义工具的最佳实践。
        
        Args:
            tool_id: 工具的唯一 ID，将作为大模型调用的标识。
            
        Returns:
            Callable: 装饰器函数。
        """
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            # 1. 构造工具适配器 (内部自动完成 Schema 推导)
            pytool = FunctionPyTool(tool_id=tool_id, func=func)
            # 2. 自动注册到工具表
            self._tool_registry.register(tool_id, pytool)
            # 3. 标记为已验证工具 (保持兼容性，但内部已完成注册)
            setattr(func, "__qfa_capability__", pytool.capability)
            return func
        return decorator

    @validate_call
    def register_pytool_instance(
        self,
        instance: Annotated[Any, Field(description="包含 @qfaos_pytool 装饰方法的类实例")],
    ) -> None:
        """
        [推荐接口] 实例注册：自动扫描并注册类实例中所有被 @qfaos_pytool 装饰的方法。
        
        适用于将多个相关工具组织在同一个类中的场景。
        
        Args:
            instance: 目标类实例。
        """
        # 此处我们不需要立即执行扫描，而是记录该实例。
        # 在 run() 阶段初始化 CapabilityHub 时，会统一调用 hub.register_instance_capabilities。
        # 为了保持 QFAOS 结构的简单，我们将其存入 tool_registry 的一个特殊集合中。
        if not hasattr(self._tool_registry, "_instances"):
            self._tool_registry._instances = []
        self._tool_registry._instances.append(instance)

    @validate_call
    def register_pytool(
        self,
        func: Annotated[Callable[..., Any], Field(description="已被 @qfaos_pytool 标记过的工具函数")],
    ) -> None:
        """
        注册一个工具函数。
        
        该函数会被转换成 SkillHub 兼容的 PyTool 协议对象。
        自动从函数的 @qfaos_pytool 标记中提取工具 ID。
        
        Args:
            func: 目标函数，必须先经过 @qfaos_pytool 装饰。
            
        Raises:
            QFAInvalidConfigError: 当函数未经过标记时抛出。
        """
        if not hasattr(func, "__qfa_capability__"):
            raise QFAInvalidConfigError("工具函数必须先使用 @qfaos_pytool 进行标记")
        
        # 提取标记中的 ID
        desc = getattr(func, "__qfa_capability__")
        tool_id = desc.capability_id

        self._tool_registry.register(tool_id, FunctionPyTool(tool_id, func))

    @validate_call
    def register_memory(
        self,
        config: Annotated[QFAConfig.Memory, Field(description="记忆配置模型")]
    ) -> None:
        """
        注册记忆策略。
        
        Args:
            config: 记忆配置对象。
        """
        self._memory_registry.register(config)

    @validate_call
    def register_observability_log(
        self,
        config: Annotated[QFAConfig.Observability.Log, Field(description="日志观测配置模型")]
    ) -> None:
        """
        注册观测日志策略。
        
        Args:
            config: 日志观测配置对象。
        """
        self._observability_registry.register_log(config)

    @validate_call(config={"arbitrary_types_allowed": True})
    def custom_execute(
        self,
        func: Annotated[
            Callable[[QFAEvent, QFAExecutionContext], Any],
            Field(description="用户定义的异步执行入口"),
        ],
    ) -> Callable[[QFAEvent, QFAExecutionContext], Any]:
        """
        注册用户自定义的执行函数。

        约束：必须为 async 函数；重复注册时覆盖旧定义。
        """
        if not iscoroutinefunction(func):
            raise QFAInvalidConfigError("custom_execute 只接受 async def 定义的异步函数")
        self._execute_handler = func
        return func

    @property
    def channels(self) -> ChannelRegistry:
        """
        获取渠道注册表实例。
        
        Returns:
            ChannelRegistry: 内部渠道注册表，可用于查询已注册的配置。
        """
        return self._channel_registry

    @property
    def models(self) -> ModelRegistry:
        """
        获取模型注册表实例。
        
        Returns:
            ModelRegistry: 内部模型注册表，可用于查询已注册的配置。
        """
        return self._model_registry

    @property
    def primitives(self) -> PrimitiveAccessor:
        """
        获取安全原语命名空间对象，可通过 agent.primitives.<primitive_id>(...) 调用原语。
        """
        return self._primitive_accessor

    @property
    def tools(self) -> ToolRegistry:
        """
        获取工具注册表实例。
        
        Returns:
            ToolRegistry: 内部工具注册表。
        """
        return self._tool_registry

    @property
    def memory(self) -> MemoryRegistry:
        """
        获取记忆注册表实例。
        
        Returns:
            MemoryRegistry: 内部记忆注册表。
        """
        return self._memory_registry

    @property
    def observability(self) -> ObservabilityRegistry:
        """
        获取观测注册表实例。
        
        Returns:
            ObservabilityRegistry: 内部观测注册表。
        """
        return self._observability_registry

    @property
    def execute_handler(self) -> Callable[[QFAEvent, QFAExecutionContext], Any] | None:
        """当前已注册的 custom_execute 处理函数。"""
        return self._execute_handler

    def run(self) -> None:
        execute_handler = self._execute_handler
        if execute_handler is None:
            raise QFAInvalidConfigError("必须先通过 @custom_execute 注册执行函数")

        feishu_cfg = self._channel_registry.get(QFAEnum.Channel.Feishu)
        if feishu_cfg is None:
            raise QFAInvalidConfigError("必须先注册飞书渠道配置")
        if not isinstance(feishu_cfg, QFAConfig.Channel.Feishu):
            raise QFAInvalidConfigError("飞书渠道配置类型错误")

        memory_cfg = self._memory_registry.get()
        if memory_cfg is None:
            raise QFAInvalidConfigError("必须先注册 memory 配置")

        log_cfg = self._observability_registry.get_log()
        if log_cfg is None:
            raise QFAInvalidConfigError("必须先注册 observability log 配置")

        model_cfg = self._model_registry.get(QFAEnum.Model.MiniMax)
        if model_cfg is None:
            raise QFAInvalidConfigError("必须先注册至少一个模型配置")
        if not isinstance(model_cfg, QFAConfig.Model.MiniMax):
            raise QFAInvalidConfigError("当前仅支持 MiniMax 模型配置")

        observability = initialize_observability_hub(
            jsonl_log_dir=log_cfg.jsonl_log_dir,
            jsonl_max_bytes=log_cfg.jsonl_max_bytes,
            jsonl_backup_count=log_cfg.jsonl_backup_count,
        )
        boot_trace_id = observability.trace_id_generator()
        boot_record = observability.record(boot_trace_id, {"event": "qfaos.run.started"}, "INFO")
        observability.jsonl_storage.write_record(boot_record)

        redis_url = memory_cfg.redis_url if memory_cfg.backend == QFAEnum.Memory.Backend.redis else None
        storage_memory = initialize_storage_memory(redis_url=redis_url, observability=observability)

        router = ModelRouter(
            clients={
                "default": InMemoryModelProviderClient(),
                model_cfg.model_name: MiniMaxModelProviderClient(
                    api_key=model_cfg.api_key,
                    model_name=model_cfg.model_name,
                    base_url=model_cfg.base_url,
                ),
            },
            observability=observability,
        )
        skill_hub = initialize_skill_hub(observability=observability)
        hub = skill_hub.capability_hub

        # 1. 自动挂载模型能力
        hub.register_instance_capabilities(router)

        # 2. 根据用户配置挂载内置工具
        if self._enable_builtin_tools:
            register_pytools(hub, (BrowserUsePyTool(),))

        # 3. 挂载用户注册的工具
        user_tools = tuple(
            self._tool_registry.get(tool_id)
            for tool_id in self._tool_registry.list_tools()
            if self._tool_registry.get(tool_id) is not None
        )
        register_pytools(hub, user_tools)

        # 注册自动扫描的类实例能力
        if hasattr(self._tool_registry, "_instances"):
            for instance in self._tool_registry._instances:
                hub.register_instance_capabilities(instance)

        oe = initialize_orchestration_engine(
            capability_hub=hub,
            storage_memory=storage_memory,
            observability=observability,
        )
        if oe.context_manager is None:
            raise QFAInvalidConfigError("orchestration_engine 未正确注入 context_manager")

        channel_gateway = initialize_channel_gateway(
            host="127.0.0.1",
            port=8000,
            feishu_settings=feishu_cfg,
            observability=observability,
        )

        orchestrator = CustomExecuteOrchestrator(
            execute_handler=execute_handler,
            storage_memory=storage_memory,
            logic_id="qfaos",
            channel_gateway=channel_gateway,
            observability=observability,
        )

        event_queue: mp.Queue = mp.Queue()

        def _worker(settings: dict[str, Any], q: mp.Queue, log_cfg_dict: dict[str, Any]) -> None:
            cfg = QFAConfig.Channel.Feishu(**settings)
            
            # 在子进程中重新初始化一个轻量级的 observability 用于记录
            # 因为 ObservabilityHubExports 包含 Callable，可能无法直接跨进程序列化
            from src.observability_hub.bootstrap import initialize as init_obs
            obs = init_obs(
                jsonl_log_dir=log_cfg_dict.get("jsonl_log_dir", "logs"),
                jsonl_max_bytes=log_cfg_dict.get("jsonl_max_bytes", 10 * 1024 * 1024),
                jsonl_backup_count=log_cfg_dict.get("jsonl_backup_count", 5),
            )

            def _on_text_event(event: Any) -> None:
                q.put(event)

            run_feishu_long_connection(cfg, _on_text_event, observability=obs)

        proc = mp.Process(
            target=_worker,
            args=(feishu_cfg.model_dump(), event_queue, log_cfg.model_dump()),
            daemon=True,
        )
        proc.start()

        async def _consume() -> None:
            while True:
                event = await asyncio.to_thread(event_queue.get)
                trace_id = observability.trace_id_generator()
                session_id = getattr(event, "logical_uid", None) or getattr(event, "user_id", "")
                ctx = await oe.context_manager.initialize_context(trace_id, "qfaos", session_id)
                updates = await orchestrator.execute(event, ctx, hub)
                oe.context_manager.update_context(ctx, updates)
                await oe.context_manager.persist_context(ctx)

        try:
            asyncio.run(_consume())
        except KeyboardInterrupt:
            pass
        finally:
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=2)
