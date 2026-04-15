from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable

from src.app.settings_store import FeishuSettings
from src.channel_gateway.channels.feishu.text_event_parser import TextEventParserFactory
from src.channel_gateway.core.domain.events import UniversalEvent


@dataclass(frozen=True)
class FeishuLongConnectionRuntime:
    """
    描述飞书长连接运行时状态的数据类。
    用于在应用启动时，向外暴露底层的 lark_oapi SDK 是否已就绪。
    """
    initialized: bool
    mode: str
    error: str | None


def parse_feishu_long_connection_event(payload: Mapping[str, Any]) -> UniversalEvent:
    """
    解析飞书 WebSocket 长连接推送的事件 JSON。
    
    该函数现已作为门面，将实际的解析工作委托给 TextEventParserFactory，
    保持了对外接口兼容性的同时，内部实现了与具体渠道结构的解耦。
    """
    parser = TextEventParserFactory.get(channel="feishu", transport="long_connection")
    return parser.parse(payload)


def run_feishu_long_connection(
    settings: FeishuSettings,
    on_text_event: Callable[[UniversalEvent], None],
) -> None:
    """
    启动并阻塞运行飞书 WebSocket 客户端。
    
    底层强依赖飞书官方的 `lark_oapi` 库。通过事件调度器 (EventDispatcher)
    注册消息接收回调，当收到消息时，通过工厂解析并抛给上层传入的 `on_text_event` 处理器。
    """
    try:
        import lark_oapi as lark
    except ImportError as error:
        raise RuntimeError("missing_lark_oapi_dependency") from error

    def _event_handler(data: Any) -> None:
        """
        桥接函数：将 lark_oapi 的内部事件对象转换为字典，
        然后使用解析工厂统一解析，并触发上层回调。
        """
        payload = _to_mapping(data)

        from src.channel_gateway.core.session.context import session_context_controller
        import dataclasses

        # 去解析所收到的原始字典数据
        event = parse_feishu_long_connection_event(payload)

        if session_context_controller.is_duplicate(event.message_id):
            return

        event = dataclasses.replace(event, logical_uid=session_context_controller.get_logical_uuid(event.user_id))

        on_text_event(event)

    # 构建飞书事件调度器，注册 V1 版本的消息接收事件
    event_dispatcher = (
        lark.EventDispatcherHandler.builder(
            settings.verify_token or "",
            settings.encrypt_key or "",
        )
        .register_p2_im_message_receive_v1(_event_handler)
        .build()
    )
    
    # 实例化并启动 WebSocket 客户端 (此方法内部会阻塞主线程，目前依赖上层 asyncio.to_thread 进行并发调度)
    ws_client = lark.ws.Client(
        settings.app_id,
        settings.app_secret,
        event_handler=event_dispatcher,
        log_level=lark.LogLevel.INFO,
    )
    ws_client.start()


def initialize_feishu_long_connection() -> FeishuLongConnectionRuntime:
    """
    探测飞书长连接依赖是否满足。
    此方法用于启动前置检查，避免在运行时抛出晦涩的包缺失错误。
    """
    try:
        import lark_oapi
    except ImportError:
        return FeishuLongConnectionRuntime(
            initialized=False,
            mode="websocket",
            error="missing_lark_oapi_dependency",
        )
    return FeishuLongConnectionRuntime(
        initialized=True,
        mode="websocket",
        error=None,
    )


def _to_mapping(data: Any) -> dict[str, Any]:
    """
    兼容性辅助函数：将各种形式的数据（字典、Pydantic 模型、普通对象）
    安全地转换为 dict 格式，以供后续按 Key 提取解析。
    这对于将第三方库不透明的内部对象剥离出纯数据非常有效。
    """
    if isinstance(data, Mapping):
        return dict(data)
    model_dump = getattr(data, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    dict_method = getattr(data, "dict", None)
    if callable(dict_method):
        dumped = dict_method()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    as_dict = _to_plain_dict(data)
    if isinstance(as_dict, Mapping):
        return dict(as_dict)
    raise ValueError("unable_to_convert_event_to_mapping")


def _to_plain_dict(data: Any) -> Any:
    """递归地将任意对象转换为普通字典，忽略私有属性"""
    if isinstance(data, Mapping):
        return {str(k): _to_plain_dict(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_to_plain_dict(v) for v in data]
    if isinstance(data, tuple):
        return tuple(_to_plain_dict(v) for v in data)
    if hasattr(data, "__dict__"):
        return {
            key: _to_plain_dict(value)
            for key, value in vars(data).items()
            if not key.startswith("_")
        }
    return data
