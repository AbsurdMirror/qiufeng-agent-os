import pytest
from pydantic import BaseModel

from src.model_provider.schema_validator import (
    AutoHealingMaxRetriesExceeded,
    SchemaValidationError,
    validate_and_heal,
)


class _DemoSchema(BaseModel):
    title: str
    score: int


def test_mp_t5_01_strips_json_code_fence_and_validates():
    """测试项 MP-T5-01: 剥离 ```json 代码块后可解析"""
    raw = """```json
{"title": "ok", "score": 1}
```"""
    model = validate_and_heal(_DemoSchema, raw)
    assert model.title == "ok"
    assert model.score == 1


def test_mp_t5_02_without_healing_func_raises_schema_validation_error():
    """测试项 MP-T5-02: 无自愈时校验失败"""
    with pytest.raises(SchemaValidationError):
        validate_and_heal(_DemoSchema, '{"title": "x"}', healing_func=None)


def test_mp_t5_03_healing_func_can_fix_and_eventually_succeed():
    """测试项 MP-T5-03: 自愈重试后成功"""
    attempts: list[str] = []

    def healer(bad_input: str, err: str) -> str:
        attempts.append(err)
        return '{"title": "fixed", "score": 2}'

    model = validate_and_heal(_DemoSchema, '{"title": "x"}', healing_func=healer, max_retries=2)
    assert model.title == "fixed"
    assert model.score == 2
    assert len(attempts) == 1


def test_mp_t5_04_fail_fast_on_auth_like_errors():
    """测试项 MP-T5-04: 自愈 fail-fast"""
    def healer(bad_input: str, err: str) -> str:
        raise RuntimeError("Authentication failed: api key missing")

    with pytest.raises(RuntimeError):
        validate_and_heal(_DemoSchema, '{"title": "x"}', healing_func=healer, max_retries=3)


def test_mp_t5_05_max_retries_semantics_is_retries_plus_first_attempt():
    """测试项 MP-T5-05: max_retries 语义"""
    calls = {"n": 0}

    def healer(bad_input: str, err: str) -> str:
        calls["n"] += 1
        return '{"title": "x"}'

    with pytest.raises(AutoHealingMaxRetriesExceeded):
        validate_and_heal(_DemoSchema, '{"title": "x"}', healing_func=healer, max_retries=2)

    assert calls["n"] == 2

