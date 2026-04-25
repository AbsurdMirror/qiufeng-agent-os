from typing import Annotated, Union

from pydantic import BaseModel, Field, field_validator

from .enums import QFAEnum


class _QFAChannelFeishuConfig(BaseModel):
    app_id: Annotated[str, Field(description="飞书 App ID")]
    app_secret: Annotated[str, Field(description="飞书 App Secret")]
    mode: Annotated[
        QFAEnum.Feishu.Mode,
        Field(description="飞书运行模式：long_connection 或 webhook"),
    ]
    verify_token: Annotated[
        str | None,
        Field(default=None, description="Webhook 校验 token；长连接模式下允许为空"),
    ] = None
    encrypt_key: Annotated[
        str | None,
        Field(default=None, description="Webhook 加密 key；长连接模式下允许为空"),
    ] = None

    @field_validator("verify_token", "encrypt_key")
    @classmethod
    def _normalize_empty(cls, value: str | None) -> str | None:
        if value == "":
            return None
        return value


class _QFAModelMiniMaxConfig(BaseModel):
    model_name: Annotated[str, Field(description="MiniMax 模型名称，例如 MiniMax-Text-01")]
    api_key: Annotated[str, Field(description="MiniMax API Key")]
    base_url: Annotated[
        str,
        Field(default="https://api.minimax.chat/v1", description="MiniMax Base URL"),
    ] = "https://api.minimax.chat/v1"


class _QFAMemoryConfig(BaseModel):
    backend: Annotated[
        QFAEnum.Memory.Backend,
        Field(description="记忆后端：in_memory 或 redis"),
    ]
    redis_url: Annotated[
        str | None,
        Field(
            default=None,
            description="Redis 连接地址；为空时回退到环境变量 REDIS_URL 或默认值",
        ),
    ] = None


class _QFAObservabilityLogConfig(BaseModel):
    jsonl_log_dir: Annotated[
        str,
        Field(default="logs", description="JSONL 日志目录"),
    ] = "logs"
    jsonl_max_bytes: Annotated[
        int,
        Field(default=10 * 1024 * 1024, ge=1, description="单个 JSONL 文件最大字节数"),
    ] = 10 * 1024 * 1024
    jsonl_backup_count: Annotated[
        int,
        Field(default=5, ge=1, description="JSONL 轮转备份数量"),
    ] = 5


class _QFABuiltinToolsConfig(BaseModel):
    enable: Annotated[
        bool,
        Field(default=False, description="是否启用全部内置工具（如浏览器工具等）"),
    ] = False


class QFAConfig:
    """
    QFAOS SDK 全局配置模型集合。
    
    采用 Pydantic V2 编写，支持自动校验、环境变量映射及 IDE 智能提示。
    """
    BuiltinTools = _QFABuiltinToolsConfig

    class Channel:
        """渠道相关配置模型。"""
        Feishu = _QFAChannelFeishuConfig

    # 定义渠道配置的联合类型，方便 Pydantic 校验和 IDE 提示
    ChannelConfigUnion = Union[_QFAChannelFeishuConfig]

    class Model:
        """模型服务相关配置模型。"""
        MiniMax = _QFAModelMiniMaxConfig

    # 定义模型配置的联合类型，方便 Pydantic 校验和 IDE 提示
    ModelConfigUnion = Union[_QFAModelMiniMaxConfig]

    # 记忆存储相关配置模型
    Memory = _QFAMemoryConfig

    class Observability:
        """观测中心相关配置模型。"""
        Log = _QFAObservabilityLogConfig
