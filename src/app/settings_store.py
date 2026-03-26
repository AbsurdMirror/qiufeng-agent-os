from dataclasses import asdict, dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class FeishuSettings:
    app_id: str
    app_secret: str
    verify_token: str | None
    encrypt_key: str | None


@dataclass(frozen=True)
class AppSettings:
    app_name: str
    environment: str
    debug: bool
    host: str
    port: int
    feishu: FeishuSettings | None


def save_app_settings(settings: AppSettings, file_path: str) -> Path:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "app_name": settings.app_name,
        "environment": settings.environment,
        "debug": settings.debug,
        "host": settings.host,
        "port": settings.port,
        "feishu": asdict(settings.feishu) if settings.feishu is not None else None,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_app_settings(file_path: str) -> AppSettings | None:
    path = Path(file_path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    app_name = data.get("app_name")
    environment = data.get("environment")
    debug = data.get("debug")
    host = data.get("host")
    port = data.get("port")
    feishu = _parse_feishu(data.get("feishu"))
    if feishu is None:
        feishu = _parse_feishu(data)
    if not isinstance(app_name, str):
        app_name = "qiufeng-agent-os"
    if not isinstance(environment, str):
        environment = "development"
    if not isinstance(debug, bool):
        debug = False
    if not isinstance(host, str):
        host = "0.0.0.0"
    if not isinstance(port, int):
        port = 8080
    return AppSettings(
        app_name=app_name,
        environment=environment,
        debug=debug,
        host=host,
        port=port,
        feishu=feishu,
    )


def save_feishu_settings(settings: FeishuSettings, file_path: str) -> Path:
    loaded = load_app_settings(file_path)
    if loaded is None:
        base = AppSettings(
            app_name="qiufeng-agent-os",
            environment="development",
            debug=False,
            host="0.0.0.0",
            port=8080,
            feishu=settings,
        )
    else:
        base = AppSettings(
            app_name=loaded.app_name,
            environment=loaded.environment,
            debug=loaded.debug,
            host=loaded.host,
            port=loaded.port,
            feishu=settings,
        )
    return save_app_settings(base, file_path)


def load_feishu_settings(file_path: str) -> FeishuSettings | None:
    loaded = load_app_settings(file_path)
    if loaded is not None and loaded.feishu is not None:
        return loaded.feishu
    path = Path(file_path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return _parse_feishu(data)


def _parse_feishu(data: object) -> FeishuSettings | None:
    if not isinstance(data, dict):
        return None
    app_id = data.get("app_id")
    app_secret = data.get("app_secret")
    if not isinstance(app_id, str) or not app_id:
        return None
    if not isinstance(app_secret, str) or not app_secret:
        return None
    verify_token = data.get("verify_token")
    encrypt_key = data.get("encrypt_key")
    if verify_token is not None and not isinstance(verify_token, str):
        verify_token = None
    if encrypt_key is not None and not isinstance(encrypt_key, str):
        encrypt_key = None
    return FeishuSettings(
        app_id=app_id,
        app_secret=app_secret,
        verify_token=verify_token,
        encrypt_key=encrypt_key,
    )
