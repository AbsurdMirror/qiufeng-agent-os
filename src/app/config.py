from dataclasses import dataclass
from os import getenv

from src.app.settings_store import AppSettings, FeishuSettings, load_app_settings


def _to_bool(value: str) -> bool:
    """
    将字符串转换为布尔值，支持常见的真值表示。
    """
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    """
    全局应用配置类。
    包含了应用的基础网络配置、环境变量标识以及第三方服务（如飞书）的凭证。
    
    Attributes:
        app_name: 应用名称，默认为 "qiufeng-agent-os"
        environment: 运行环境，如 "development" 或 "production"
        debug: 是否开启调试模式
        host: 服务监听地址，默认 "0.0.0.0"
        port: 服务监听端口，默认 8080
        config_file_path: 本地配置文件的存储路径（用于持久化飞书等凭证）
        feishu: 飞书应用的认证信息，若未配置则为 None
    """
    app_name: str
    environment: str
    debug: bool
    host: str
    port: int
    config_file_path: str
    feishu: FeishuSettings | None

    @classmethod
    def from_env(cls) -> "AppConfig":
        """
        从环境变量和本地配置文件中构建 AppConfig 实例。
        优先级：环境变量 > 本地配置文件。
        """
        config_file_path = getenv("QF_CONFIG_PATH", ".qf/app_settings.json")
        file_settings = load_app_settings(config_file_path)
        env_settings = _load_env_settings()
        merged_settings = _merge_settings(file_settings, env_settings)
        return cls(
            app_name=merged_settings.app_name,
            environment=merged_settings.environment,
            debug=merged_settings.debug,
            host=merged_settings.host,
            port=merged_settings.port,
            config_file_path=config_file_path,
            feishu=merged_settings.feishu,
        )


def load_config() -> AppConfig:
    """
    加载并返回全局应用配置。
    """
    return AppConfig.from_env()


def _load_env_settings() -> AppSettings:
    app_name = getenv("QF_APP_NAME", "qiufeng-agent-os")
    environment = getenv("QF_ENV", "development")
    debug = _to_bool(getenv("QF_DEBUG", "false"))
    host = getenv("QF_HOST", "0.0.0.0")
    port = int(getenv("QF_PORT", "8080"))
    feishu = _load_env_feishu_settings()
    return AppSettings(
        app_name=app_name,
        environment=environment,
        debug=debug,
        host=host,
        port=port,
        feishu=feishu,
    )


def _load_env_feishu_settings() -> FeishuSettings | None:
    env_app_id = getenv("QF_FEISHU_APP_ID")
    env_app_secret = getenv("QF_FEISHU_APP_SECRET")
    env_verify_token = getenv("QF_FEISHU_VERIFY_TOKEN")
    env_encrypt_key = getenv("QF_FEISHU_ENCRYPT_KEY")
    if not env_app_id or not env_app_secret:
        return None
    return FeishuSettings(
        app_id=env_app_id,
        app_secret=env_app_secret,
        verify_token=env_verify_token,
        encrypt_key=env_encrypt_key,
    )


def _merge_settings(file_settings: AppSettings | None, env_settings: AppSettings) -> AppSettings:
    if file_settings is None:
        return env_settings
    return AppSettings(
        app_name=file_settings.app_name,
        environment=file_settings.environment,
        debug=file_settings.debug,
        host=file_settings.host,
        port=file_settings.port,
        feishu=file_settings.feishu if file_settings.feishu is not None else env_settings.feishu,
    )
