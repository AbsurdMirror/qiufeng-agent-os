import sys
from unittest.mock import MagicMock
sys.modules['pydantic'] = MagicMock()
from src.skill_hub.security import default_security_policy, with_security_policy, SecurityError, SecurityApprovalRequiredError
from src.orchestration_engine.contracts import CapabilityRequest, CapabilityResult
import asyncio

async def run_test():
    policy = default_security_policy

    @with_security_policy(policy)
    async def my_tool(req: CapabilityRequest) -> CapabilityResult:
        fs = req.metadata["secure_fs"]
        fs.check_path_policy("/etc/passwd", "read") # should raise SecurityError
        return CapabilityResult("test", True, {}, None, None, {})

    req = CapabilityRequest("test", {}, {"workspace": "/tmp/test"})
    res = await my_tool(req)
    print("Blacklist test result:", res.error_code)

    @with_security_policy(policy)
    async def my_tool_grey(req: CapabilityRequest) -> CapabilityResult:
        shell = req.metadata["secure_shell"]
        shell.check_command_policy("apt-get install tree") # should raise SecurityApprovalRequiredError
        return CapabilityResult("test", True, {}, None, None, {})

    res2 = await my_tool_grey(req)
    print("Greylist test result:", res2.error_code, res2.metadata.get("ticket_id"))

    ticket_id = res2.metadata.get("ticket_id")
    policy.ticket_store.approve_ticket(ticket_id)

    req3 = CapabilityRequest("test", {}, {"workspace": "/tmp/test", "ticket_id": ticket_id})
    res3 = await my_tool_grey(req3)
    print("Greylist approved test result:", res3.success)

asyncio.run(run_test())
