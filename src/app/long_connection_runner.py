import asyncio
import json

from src.app.bootstrap import Application
from src.channel_gateway.core.domain.events import UniversalEvent


def run_feishu_long_connection(app: Application) -> None:
    asyncio.run(_run_feishu_long_connection_async(app))


async def _run_feishu_long_connection_async(app: Application) -> None:
    if app.config.feishu is None:
        raise RuntimeError("missing_feishu_settings")

    gateway = app.modules.channel_gateway
    observability = app.modules.observability_hub
    trace_id_generator = observability.trace_id_generator
    recorder = observability.record
    run_entry = gateway.run_feishu_long_connection
    runtime = gateway.feishu_long_connection

    if not runtime.initialized:
        error = runtime.error or "feishu_long_connection_unavailable"
        raise RuntimeError(error)

    queue: asyncio.Queue[UniversalEvent] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _on_text_event(event: UniversalEvent) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    async def _consume_event_loop() -> None:
        while True:
            event = await queue.get()
            trace_id = trace_id_generator()
            recorder(
                trace_id=trace_id,
                data={
                    "event_type": "feishu_text_long_connection",
                    "event_id": event.event_id,
                    "message_id": event.message_id,
                    "user_id": event.user_id,
                    "text": event.text,
                },
                level="INFO",
            )
            print(
                json.dumps(
                    {
                        "trace_id": trace_id,
                        "platform": event.platform_type,
                        "event_id": event.event_id,
                        "user_id": event.user_id,
                        "text": event.text,
                    },
                    ensure_ascii=False,
                )
            )

    async def _run_long_connection() -> None:
        await asyncio.to_thread(
            run_entry,
            app.config.feishu,
            _on_text_event,
        )

    print(f"{app.config.app_name} feishu long connection starting")
    print(f"feishu app_id loaded: {app.config.feishu.app_id}")
    await asyncio.gather(_consume_event_loop(), _run_long_connection())
