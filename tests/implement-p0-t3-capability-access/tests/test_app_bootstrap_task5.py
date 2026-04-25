from types import SimpleNamespace

from tests.support_qfaos_bootstrap import (
    QFAOSBootstrapConfig,
    build_qfaos_application,
)


def test_app_01_build_application_injects_skill_hub_into_orchestration(monkeypatch):
    """测试项 APP-01: qfaos 装配链路将 Skill Hub 能力中心注入编排层"""
    captured: dict[str, object] = {}
    fake_channel_gateway = SimpleNamespace(layer="channel_gateway")
    fake_model_provider = SimpleNamespace(layer="model_provider", client=object())
    fake_capability_hub = object()
    fake_skill_hub = SimpleNamespace(layer="skill_hub", capability_hub=fake_capability_hub)
    fake_storage_memory = SimpleNamespace(layer="storage_memory")
    fake_observability_hub = SimpleNamespace(layer="observability_hub")

    def fake_initialize_skill_hub() -> object:
        return fake_skill_hub

    def fake_initialize_orchestration_engine(*, capability_hub: object, **kwargs) -> object:
        captured["capability_hub"] = capability_hub
        return SimpleNamespace(layer="orchestration_engine", capability_hub=capability_hub)

    monkeypatch.setattr(
        "tests.support_qfaos_bootstrap.initialize_channel_gateway",
        lambda host, port, **kwargs: fake_channel_gateway,
    )
    monkeypatch.setattr(
        "tests.support_qfaos_bootstrap.initialize_model_provider",
        lambda: fake_model_provider,
    )
    monkeypatch.setattr(
        "tests.support_qfaos_bootstrap.initialize_skill_hub",
        fake_initialize_skill_hub,
    )
    monkeypatch.setattr(
        "tests.support_qfaos_bootstrap.initialize_orchestration_engine",
        fake_initialize_orchestration_engine,
    )
    monkeypatch.setattr(
        "tests.support_qfaos_bootstrap.initialize_storage_memory",
        lambda **kwargs: fake_storage_memory,
    )
    monkeypatch.setattr(
        "tests.support_qfaos_bootstrap.initialize_observability_hub",
        lambda: fake_observability_hub,
    )

    app = build_qfaos_application(
        QFAOSBootstrapConfig(
            app_name="qiufeng-agent-os",
            environment="test",
            debug=False,
            host="127.0.0.1",
            port=8080,
            config_file_path=".qf/test.json",
            feishu=None,
        )
    )

    assert app.modules.model_provider is fake_model_provider
    assert app.modules.skill_hub is fake_skill_hub
    assert app.modules.orchestration_engine.capability_hub is fake_capability_hub
    assert captured["capability_hub"] is fake_capability_hub
