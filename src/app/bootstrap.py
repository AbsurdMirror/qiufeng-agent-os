from dataclasses import dataclass

from src.app.config import AppConfig
from src.channel_gateway.exports import ChannelGatewayExports
from src.channel_gateway import initialize as initialize_channel_gateway
from src.model_provider.exports import ModelProviderExports
from src.model_provider import initialize as initialize_model_provider
from src.observability_hub.exports import ObservabilityHubExports
from src.observability_hub import initialize as initialize_observability_hub
from src.orchestration_engine.exports import OrchestrationEngineExports
from src.orchestration_engine import initialize as initialize_orchestration_engine
from src.storage_memory.exports import StorageMemoryExports
from src.storage_memory import initialize as initialize_storage_memory


@dataclass(frozen=True)
class AppModules:
    channel_gateway: ChannelGatewayExports
    orchestration_engine: OrchestrationEngineExports
    model_provider: ModelProviderExports
    storage_memory: StorageMemoryExports
    observability_hub: ObservabilityHubExports


@dataclass(frozen=True)
class Application:
    """
    全局应用上下文容器，作为单例在整个应用生命周期中传递。
    包含了应用的基础配置信息，以及各个核心模块初始化后暴露出来的接口/实例。
    
    Attributes:
        config (AppConfig): 启动时加载的环境变量和系统配置。
        modules (dict[str, dict[str, Any]]): 存储各个子模块初始化的结果，
            通常包含 NoneBot 实例、注册中心实例或全局拦截器等。
    """
    config: AppConfig
    modules: AppModules


def build_application(config: AppConfig) -> Application:
    """
    应用的启动引导(Bootstrap)函数。
    按照架构分层规范，依次调用各层的 initialize() 初始化方法，
    组装并返回一个完整的 Application 上下文对象。

    Args:
        config (AppConfig): 系统配置对象

    Returns:
        Application: 组装完成的应用上下文
    """
    modules = AppModules(
        channel_gateway=initialize_channel_gateway(host=config.host, port=config.port),
        orchestration_engine=initialize_orchestration_engine(),
        model_provider=initialize_model_provider(),
        storage_memory=initialize_storage_memory(),
        observability_hub=initialize_observability_hub(),
    )
    return Application(config=config, modules=modules)
