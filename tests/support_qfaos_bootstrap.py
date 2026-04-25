from dataclasses import dataclass

from src.channel_gateway import initialize as initialize_channel_gateway
from src.channel_gateway.exports import ChannelGatewayExports
from src.model_provider import initialize as initialize_model_provider
from src.model_provider.exports import ModelProviderExports
from src.observability_hub import initialize as initialize_observability_hub
from src.observability_hub.exports import ObservabilityHubExports
from src.orchestration_engine import initialize as initialize_orchestration_engine
from src.orchestration_engine.exports import OrchestrationEngineExports
from src.skill_hub import initialize as initialize_skill_hub
from src.skill_hub.exports import SkillHubExports
from src.storage_memory import initialize as initialize_storage_memory
from src.storage_memory.exports import StorageMemoryExports


@dataclass(frozen=True)
class QFAOSBootstrapConfig:
    app_name: str
    environment: str
    debug: bool
    host: str
    port: int
    config_file_path: str = ".qf/settings.json"
    feishu: object | None = None
    redis_url: str | None = None


@dataclass(frozen=True)
class QFAOSModules:
    channel_gateway: ChannelGatewayExports
    model_provider: ModelProviderExports
    skill_hub: SkillHubExports
    orchestration_engine: OrchestrationEngineExports
    storage_memory: StorageMemoryExports
    observability_hub: ObservabilityHubExports


@dataclass(frozen=True)
class QFAOSApplication:
    config: QFAOSBootstrapConfig
    modules: QFAOSModules


def build_qfaos_application(config: QFAOSBootstrapConfig) -> QFAOSApplication:
    channel_gateway = initialize_channel_gateway(
        host=config.host,
        port=config.port,
        feishu_settings=config.feishu,
    )
    model_provider = initialize_model_provider()
    skill_hub = initialize_skill_hub()
    storage_memory = initialize_storage_memory(redis_url=config.redis_url)
    orchestration_engine = initialize_orchestration_engine(
        capability_hub=skill_hub.capability_hub,
        storage_memory=storage_memory,
    )
    observability_hub = initialize_observability_hub()

    return QFAOSApplication(
        config=config,
        modules=QFAOSModules(
            channel_gateway=channel_gateway,
            model_provider=model_provider,
            skill_hub=skill_hub,
            orchestration_engine=orchestration_engine,
            storage_memory=storage_memory,
            observability_hub=observability_hub,
        ),
    )
