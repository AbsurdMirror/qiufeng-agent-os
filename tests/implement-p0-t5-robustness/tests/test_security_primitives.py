import asyncio

import pytest

from src.orchestration_engine.contracts import CapabilityRequest, CapabilityResult
from src.skill_hub.primitives.security import (
    SecurityApprovalRequiredError,
    SecurityError,
    PolicyDecision,
    TicketStore,
    ToolSecurityPrimitive,
    create_secure_action,
    with_security_policy,
)


def test_sh_t5_01_ticket_store_generate_and_consume(monkeypatch):
    """测试项 SH-T5-01: TicketStore 生成/有效/核销"""
    store = TicketStore(ttl_seconds=10)

    now = 1000.0
    monkeypatch.setattr("src.skill_hub.primitives.security.time.time", lambda: now)

    tid = store.generate()
    assert store.is_valid(tid) is True

    store.consume(tid)
    assert store.is_valid(tid) is False


def test_sh_t5_01_ticket_store_expires(monkeypatch):
    store = TicketStore(ttl_seconds=1)

    now = 2000.0
    monkeypatch.setattr("src.skill_hub.primitives.security.time.time", lambda: now)

    tid = store.generate()
    assert store.is_valid(tid) is True

    now = 2002.0
    assert store.is_valid(tid) is False


def test_sh_t5_02_create_secure_action_requires_ticket_then_allows_with_ticket(monkeypatch):
    """测试项 SH-T5-02: create_secure_action 灰名单流程"""
    store = TicketStore(ttl_seconds=10)
    monkeypatch.setattr("src.skill_hub.primitives.security.time.time", lambda: 3000.0)

    def policy(x: int):
        return PolicyDecision.REQUIRE_TICKET, "need approval"

    def action(x: int) -> int:
        return x + 1

    secured = create_secure_action(action, policy, ticket_store=store)

    with pytest.raises(SecurityApprovalRequiredError) as e:
        secured(1)
    tid = e.value.ticket_id
    assert store.is_valid(tid) is True

    assert secured(1, approved_ticket_id=tid) == 2


def test_sh_t5_03_with_security_policy_maps_to_capability_result_and_consumes_ticket():
    """测试项 SH-T5-03/04: with_security_policy 映射与 ticket 核销"""
    policy = ToolSecurityPrimitive(working_dir=".")
    wrapped = with_security_policy(policy)

    async def handler(req: CapabilityRequest) -> CapabilityResult:
        cmd = req.payload.get("command", "")
        output = policy.secure_shell.execute(cmd, approved_ticket_id=req.ticket_id)
        return CapabilityResult(capability_id=req.capability_id, success=True, output={"stdout": output})

    secured_handler = wrapped(handler)

    req = CapabilityRequest(capability_id="tool.test.shell.exec", payload={"command": "pwd"}, metadata={})
    result1 = asyncio.run(secured_handler(req))
    assert result1.success is False
    assert result1.error_code == "requires_user_approval"
    ticket_id = result1.metadata.get("ticket_id")
    assert isinstance(ticket_id, str) and ticket_id

    req2 = CapabilityRequest(
        capability_id="tool.test.shell.exec",
        payload={"command": "pwd"},
        metadata={},
        ticket_id=ticket_id,
    )
    result2 = asyncio.run(secured_handler(req2))
    assert result2.success is True
    assert "stdout" in result2.output

    result3 = asyncio.run(secured_handler(req2))
    assert result3.success is False
    assert result3.error_code == "requires_user_approval"
    assert result3.metadata.get("ticket_id") != ticket_id


def test_sh_t5_03_with_security_policy_maps_deny_to_security_policy_violation():
    policy = ToolSecurityPrimitive(working_dir=".", shell_blacklist=["rm"])
    wrapped = with_security_policy(policy)

    async def handler(req: CapabilityRequest) -> CapabilityResult:
        cmd = req.payload.get("command", "")
        output = policy.secure_shell.execute(cmd, approved_ticket_id=req.ticket_id)
        return CapabilityResult(capability_id=req.capability_id, success=True, output={"stdout": output})

    secured_handler = wrapped(handler)

    result = asyncio.run(
        secured_handler(CapabilityRequest(capability_id="tool.test.shell.exec", payload={"command": "rm -rf /"}, metadata={}))
    )
    assert result.success is False
    assert result.error_code == "security_policy_violation"
