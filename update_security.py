with open("src/skill_hub/security.py", "w") as f:
    f.write('''from collections.abc import Callable, Awaitable
from typing import Any
import functools
import os
import uuid
from pathlib import Path
from src.orchestration_engine.contracts import CapabilityRequest, CapabilityResult

# ============================================================
# 能力中心 —— 安全原语 (Security Primitive)
#
# 本模块实现了规格 SH-P0-01（PyTools 安全原语实现）。
#
# 设计意图：
#   在大模型调用本地工具链（尤其是文件读写、沙盒执行等）时，需要提供安全管控能力。
#   本模块提供：
#   1. SecureFileSystem / SecureShell: 受限环境 SDK，拦截越权及高危操作。
#   2. ToolSecurityPrimitive: 安全策略引擎与 Ticket Store 闭环。
#   3. with_security_policy: 用于拦截非法调用并支持 Ticket 重试的函数装饰器。
#
# 使用方式：
#   在注册工具时，使用装饰器包装实际处理函数：
#   @with_security_policy(default_security_policy)
#   async def my_tool_handler(req: CapabilityRequest) -> CapabilityResult:
#       ...
# ============================================================


class SecurityError(Exception):
    """
    安全策略拦截异常（黑名单完全拦截）。
    当请求触发严重安全违规（如 Path Traversal、恶意系统指令）时抛出。
    """
    pass


class SecurityApprovalRequiredError(Exception):
    """
    安全审批要求异常（灰名单挂起）。
    当请求触发灰名单策略时，挂起真实操作并向上传递需要人工确认的 Ticket ID。
    """
    def __init__(self, ticket_id: str, message: str):
        super().__init__(message)
        self.ticket_id = ticket_id


class TicketStore:
    """内部凭证存储，用于记录并核销灰名单操作。"""
    def __init__(self):
        self._tickets: dict[str, dict] = {}

    def issue_ticket(self, action_type: str, details: dict) -> str:
        ticket_id = f"TICKET_{uuid.uuid4().hex[:8]}"
        self._tickets[ticket_id] = {
            "status": "pending",
            "action": action_type,
            "details": details
        }
        return ticket_id

    def approve_ticket(self, ticket_id: str) -> bool:
        if ticket_id in self._tickets:
            self._tickets[ticket_id]["status"] = "approved"
            return True
        return False

    def check_and_consume_ticket(self, ticket_id: str) -> bool:
        """检查凭证是否已被授权，若是则消耗掉并返回 True。"""
        if ticket_id in self._tickets and self._tickets[ticket_id]["status"] == "approved":
            # 核销机制：一次性消耗
            del self._tickets[ticket_id]
            return True
        return False


class SecureFileSystem:
    """安全文件系统 SDK。"""
    def __init__(self, session_workspace: str, ticket_store: TicketStore, request_ticket_id: str | None = None):
        self.workspace = Path(session_workspace).resolve()
        self.ticket_store = ticket_store
        self.request_ticket_id = request_ticket_id

    def check_path_policy(self, path: str, action: str = "read") -> None:
        """
        三级名单检查：
        Blacklist: Path Traversal, `/etc/`, `/root/`
        Whitelist: Inside session_workspace, or readonly in `/tmp`
        Greylist: Other places
        """
        target = Path(path).resolve()
        target_str = str(target)

        # Blacklist Checks
        if "/etc/" in target_str or target_str.startswith("/root") or target_str.startswith("/var/run"):
            raise SecurityError(f"Access to sensitive path blocked: {path}")

        # Whitelist Checks
        if target_str.startswith(str(self.workspace)):
            return # Safe to proceed

        if action == "read" and (target_str.startswith("/tmp") or target_str.startswith("/opt")):
            return

        # Greylist Checks (needs approval)
        if self.request_ticket_id and self.ticket_store.check_and_consume_ticket(self.request_ticket_id):
            return # Ticket was approved, let it pass

        # Not approved, issue new ticket
        ticket = self.ticket_store.issue_ticket("fs_access", {"path": target_str, "action": action})
        raise SecurityApprovalRequiredError(ticket, f"Action requires user approval. Path: {target_str}")


class SecureShell:
    """安全命令行 SDK。"""
    def __init__(self, ticket_store: TicketStore, request_ticket_id: str | None = None):
        self.ticket_store = ticket_store
        self.request_ticket_id = request_ticket_id

        self.blacklist_prefixes = ["rm -rf /", "mkfs", "chmod -R 777 /", "passwd"]
        self.whitelist_commands = ["ls", "pwd", "echo", "cat", "git status", "python --version"]

    def check_command_policy(self, command: str) -> None:
        """
        三级名单检查：
        Blacklist: High risk commands like `rm -rf /`
        Whitelist: Safe, read-only commands
        Greylist: Anything else (state changing or unknown)
        """
        cmd_stripped = command.strip()

        # Blacklist Checks
        for bl in self.blacklist_prefixes:
            if cmd_stripped.startswith(bl):
                raise SecurityError(f"Execution of dangerous command blocked: {command}")

        # Whitelist Checks
        for wl in self.whitelist_commands:
            if cmd_stripped == wl or cmd_stripped.startswith(wl + " "):
                # Extra check for cat to ensure it doesn't read sensitive files
                if cmd_stripped.startswith("cat "):
                    if "/etc/shadow" in cmd_stripped or "/etc/passwd" in cmd_stripped:
                        raise SecurityError(f"Execution of dangerous command blocked: {command}")
                return # Safe

        # Greylist Checks (needs approval)
        if self.request_ticket_id and self.ticket_store.check_and_consume_ticket(self.request_ticket_id):
            return # Ticket was approved, let it pass

        # Not approved, issue new ticket
        ticket = self.ticket_store.issue_ticket("shell_exec", {"command": command})
        raise SecurityApprovalRequiredError(ticket, f"Command execution requires user approval: {command}")


class ToolSecurityPrimitive:
    """
    (SH-P0-01) PyTools 安全原语实现。
    """
    def __init__(self, allowed_domains: set[str] | None = None):
        self.allowed_domains = allowed_domains or set()
        self.ticket_store = TicketStore()

    def create_fs(self, session_workspace: str, request_ticket_id: str | None = None) -> SecureFileSystem:
        return SecureFileSystem(session_workspace, self.ticket_store, request_ticket_id)

    def create_shell(self, request_ticket_id: str | None = None) -> SecureShell:
        return SecureShell(self.ticket_store, request_ticket_id)

    def enforce_policy(self, request: CapabilityRequest) -> None:
        """
        拦截预检（如简单的形式参数拦截或元数据检查）。
        此方法用于兼容原有装饰器逻辑，但真正的核心防御下沉到 SecureFileSystem 和 SecureShell。
        """
        if request.metadata.get("unsafe") is True:
            raise SecurityError(f"Capability '{request.capability_id}' execution denied due to 'unsafe' metadata flag.")


def with_security_policy(policy: ToolSecurityPrimitive) -> Callable:
    """
    安全策略拦截器（装饰器）。

    包裹基础的 Capability handler。在正式执行 handler 逻辑前，
    调用 policy 引擎进行安全校验。如果校验失败，将 SecurityError 转化为
    平滑降级的 CapabilityResult；如果触发灰名单，将其转化为审批请求。
    """
    def decorator(handler: Callable[[CapabilityRequest], Awaitable[CapabilityResult]]) -> Callable[[CapabilityRequest], Awaitable[CapabilityResult]]:
        @functools.wraps(handler)
        async def wrapper(request: CapabilityRequest) -> CapabilityResult:
            try:
                # 预检
                policy.enforce_policy(request)

                # 注入安全 SDK 到 request 供底层的 PyTools 使用
                # (工具内部可以直接从 request.metadata 取出 sdk 实例)
                ticket_id = request.metadata.get("ticket_id")
                # 默认 workspace 策略
                workspace = request.metadata.get("workspace", "/tmp/agent_workspace")

                request.metadata["secure_fs"] = policy.create_fs(workspace, ticket_id)
                request.metadata["secure_shell"] = policy.create_shell(ticket_id)

                # 执行具体业务逻辑
                return await handler(request)

            except SecurityApprovalRequiredError as e:
                # 灰名单拦截，需要人类审批
                return CapabilityResult(
                    capability_id=request.capability_id,
                    success=False,
                    output={},
                    error_code="requires_user_approval",
                    error_message=str(e),
                    metadata={"ticket_id": e.ticket_id}
                )
            except SecurityError as e:
                # 黑名单拦截
                return CapabilityResult(
                    capability_id=request.capability_id,
                    success=False,
                    output={},
                    error_code="security_policy_violation",
                    error_message=str(e),
                    metadata={"security_blocked": True}
                )
        return wrapper
    return decorator


# 提供一个全局默认策略实例，供简单的全局调用或默认配置使用
default_security_policy = ToolSecurityPrimitive()
''')
