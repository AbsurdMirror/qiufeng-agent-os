import argparse

from src.app.bootstrap import build_application
from src.app.bootstrap import Application
from src.app.config import load_config
from src.app.feishu_api import request_tenant_access_token
from src.app.long_connection_runner import run_feishu_long_connection
from src.app.settings_store import AppSettings, FeishuSettings, load_app_settings, save_app_settings
from src.app.webhook_server import run_webhook_server


def create_app():
    """
    初始化并返回全局应用上下文。
    """
    config = load_config()
    return build_application(config)


def main(argv: list[str] | None = None) -> None:
    """
    应用的主入口函数，负责解析命令行参数并分发到不同的执行逻辑。
    """
    parser = _build_cli_parser()
    args = parser.parse_args(argv)
    
    # 拦截配置命令：如果只是配置飞书，就不需要启动服务
    if args.command == "config-feishu":
        _handle_config_feishu(args)
        return
    if args.command == "config-interactive":
        _handle_config_interactive(args)
        return
        
    # 对于 run 和 run-webhook 命令，需要构建完整的应用上下文
    app = create_app()
    _print_startup_summary(app)
    
    if args.command == "run":
        try:
            run_feishu_long_connection(app)
        except RuntimeError as error:
            _print_runtime_error(str(error))
        return
        
    if args.command == "run-webhook":
        run_webhook_server(app)
        return
        
    # 如果没有匹配的子命令，打印帮助信息
    parser.print_help()


def _build_cli_parser() -> argparse.ArgumentParser:
    """
    构建命令行参数解析器。
    定义了三个子命令：run (长连接), run-webhook (Webhook), config-feishu (配置工具)。
    """
    parser = argparse.ArgumentParser(prog="python -m src.app.main")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("run")
    subparsers.add_parser("run-webhook")

    feishu_parser = subparsers.add_parser("config-feishu")
    feishu_parser.add_argument("--app-id", required=True)
    feishu_parser.add_argument("--app-secret", required=True)
    feishu_parser.add_argument("--verify-token", default=None)
    feishu_parser.add_argument("--encrypt-key", default=None)
    feishu_parser.add_argument("--config-path", default=None)

    interactive_parser = subparsers.add_parser("config-interactive")
    interactive_parser.add_argument("--config-path", default=None)
    return parser


def _handle_config_feishu(args: argparse.Namespace) -> None:
    """
    处理 `config-feishu` 子命令的逻辑。
    将用户输入的飞书凭证持久化到本地，并立刻向飞书服务器发请求校验凭证是否有效。
    """
    app = create_app()
    config_path = args.config_path or app.config.config_file_path
    settings = FeishuSettings(
        app_id=args.app_id,
        app_secret=args.app_secret,
        verify_token=args.verify_token,
        encrypt_key=args.encrypt_key,
    )
    output_path = _save_config_with_feishu(config_path=config_path, feishu=settings)
    
    # 立刻校验凭证
    ok, message = request_tenant_access_token(app_id=args.app_id, app_secret=args.app_secret)
    if ok:
        print(f"feishu 配置已写入: {output_path}")
        print("app_id/app_secret 校验成功")
        return
    print(f"feishu 配置已写入: {output_path}")
    print(f"app_id/app_secret 校验失败: {message}")


def _handle_config_interactive(args: argparse.Namespace) -> None:
    app = create_app()
    config_path = args.config_path or app.config.config_file_path
    current = app.config
    print("交互式配置开始，回车可保留当前值。")
    app_name = _prompt_text("应用名称", current.app_name)
    environment = _prompt_choice("运行环境", ["development", "staging", "production"], current.environment)
    debug = _prompt_choice("调试模式", ["false", "true"], "true" if current.debug else "false") == "true"
    host = _prompt_text("监听地址", current.host)
    port = int(_prompt_text("监听端口", str(current.port)))
    has_feishu = _prompt_choice(
        "配置飞书",
        ["yes", "no"],
        "yes" if current.feishu is not None else "no",
    )
    feishu = current.feishu
    if has_feishu == "yes":
        default_app_id = current.feishu.app_id if current.feishu is not None else ""
        default_app_secret = current.feishu.app_secret if current.feishu is not None else ""
        default_verify_token = current.feishu.verify_token if current.feishu is not None else ""
        default_encrypt_key = current.feishu.encrypt_key if current.feishu is not None else ""
        app_id = _prompt_text("飞书 App ID", default_app_id)
        app_secret = _prompt_text("飞书 App Secret", default_app_secret)
        verify_token = _prompt_text("飞书 Verify Token(可空)", default_verify_token)
        encrypt_key = _prompt_text("飞书 Encrypt Key(可空)", default_encrypt_key)
        feishu = FeishuSettings(
            app_id=app_id,
            app_secret=app_secret,
            verify_token=verify_token or None,
            encrypt_key=encrypt_key or None,
        )
    else:
        feishu = None
    output_path = save_app_settings(
        AppSettings(
            app_name=app_name,
            environment=environment,
            debug=debug,
            host=host,
            port=port,
            feishu=feishu,
        ),
        config_path,
    )
    print(f"配置已写入: {output_path}")
    if feishu is not None:
        ok, message = request_tenant_access_token(app_id=feishu.app_id, app_secret=feishu.app_secret)
        if ok:
            print("app_id/app_secret 校验成功")
        else:
            print(f"app_id/app_secret 校验失败: {message}")


def _print_startup_summary(app: Application) -> None:
    """
    打印服务启动的横幅与摘要信息，提升本地开发体验。
    """
    app_config = app.config
    print(
        f"{app_config.app_name} started in {app_config.environment} on "
        f"{app_config.host}:{app_config.port}"
    )
    print(f"feishu config file: {app_config.config_file_path}")


def _print_runtime_error(error: str) -> None:
    """
    格式化并打印运行时错误，针对常见错误给出明确的修复指引。
    """
    print(f"启动失败: {error}")
    if error == "missing_feishu_settings":
        print("请先执行: python -m src.app.main config-feishu --app-id <id> --app-secret <secret>")
        return
    if error == "missing_lark_oapi_dependency":
        print("请先安装: pip install lark-oapi")


def _save_config_with_feishu(config_path: str, feishu: FeishuSettings) -> str:
    loaded = load_app_settings(config_path)
    if loaded is not None:
        current = loaded
    else:
        runtime = load_config()
        current = AppSettings(
            app_name=runtime.app_name,
            environment=runtime.environment,
            debug=runtime.debug,
            host=runtime.host,
            port=runtime.port,
            feishu=runtime.feishu,
        )
    settings = AppSettings(
        app_name=current.app_name,
        environment=current.environment,
        debug=current.debug,
        host=current.host,
        port=current.port,
        feishu=feishu,
    )
    path = save_app_settings(settings, config_path)
    return str(path)


def _prompt_text(label: str, default_value: str) -> str:
    value = input(f"{label} [{default_value}]: ").strip()
    return value or default_value


def _prompt_choice(label: str, options: list[str], default_value: str) -> str:
    choices = "/".join(options)
    value = input(f"{label} ({choices}) [{default_value}]: ").strip().lower()
    if not value:
        return default_value
    if value not in options:
        return default_value
    return value


if __name__ == "__main__":
    main()
