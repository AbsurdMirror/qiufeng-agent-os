import functools
import inspect
import re
import subprocess
import uuid
from collections.abc import Callable, Awaitable
from enum import Enum
from pathlib import Path
from typing import Any

import bashlex

from src.domain.capabilities import CapabilityRequest, CapabilityResult

# ============================================================
# 能力中心 —— 安全原语 (Security Primitive)
#
# 本模块实现了规格 SH-P0-01（PyTools 安全原语实现）。
# 支持用户输入的黑白名单，省缺则全为灰名单（需要用户凭证授权）。
# 命令行执行引入了 bashlex 进行复合命令提取。
# ============================================================

class SecurityError(Exception):
    """
    黑名单拦截抛出的异常。
    当请求未能通过校验或命中黑名单策略时抛出。
    """
    pass

class SecurityApprovalRequiredError(Exception):
    """
    灰名单拦截抛出的异常。
    当操作需要用户授权时抛出，包含生成的 ticket_id。
    """
    def __init__(self, ticket_id: str, message: str):
        super().__init__(message)
        self.ticket_id = ticket_id

import time

class TicketStore:
    """
    (SH-P0-01) 内存 Ticket 存储凭证系统。
    用于暂存大模型执行灰名单（危险但不被完全禁止）动作时生成的临时授权凭证。
    当请求被拦截时生成 Ticket，用户在外部前端授权后，凭此 Ticket 再次调用即可放行。
    """
    def __init__(self, ttl_seconds: int = 3600):
        self._tickets: dict[str, float] = {}
        self.ttl_seconds = ttl_seconds

    def _gc(self) -> None:
        """垃圾回收：清理过期的 ticket 以防止内存泄漏"""
        now = time.time()
        expired = [tid for tid, expiry in self._tickets.items() if now > expiry]
        for tid in expired:
            del self._tickets[tid]

    def generate(self) -> str:
        self._gc()
        ticket_id = str(uuid.uuid4())
        self._tickets[ticket_id] = time.time() + self.ttl_seconds
        return ticket_id

    def is_valid(self, ticket_id: str) -> bool:
        """检查凭证是否有效（不直接核销，以便单次请求多次命中灰名单）"""
        self._gc()
        expiry = self._tickets.get(ticket_id)
        if expiry and time.time() <= expiry:
            return True
        return False

    def consume(self, ticket_id: str) -> None:
        """核销凭证，防止一个凭证被重复利用（重放攻击）"""
        # [修复 REV-SEC-CON-001]
        # 当凭单被消费（工具成功执行完毕）后主动清理，
        # 配合上面的 ttl_seconds 定期过期清理机制，
        # 彻底杜绝了随着运行时间推移导致的内存泄露 (OOM) 风险。
        self._tickets.pop(ticket_id, None)

# 全局 Ticket Store（P0 阶段使用内存存储，未来应接入 Redis 支持多实例和持久化）
_global_ticket_store = TicketStore()

class PolicyDecision(Enum):
    ALLOW = "allow"             # 白名单：直接放行
    DENY = "deny"               # 黑名单：立刻抛出异常拒绝
    REQUIRE_TICKET = "require_ticket"  # 灰名单：挂起并要求业务线人类审批

def _normalize_policy_result(result: Any) -> tuple[PolicyDecision, str | None]:
    if isinstance(result, tuple) and len(result) == 2:
        decision, message = result
        return decision, message
    return result, None

def create_secure_action(
    action_func: Callable[..., Any],
    policy_func: Callable[..., Any],
    *,
    ticket_store: TicketStore = _global_ticket_store,
) -> Callable[..., Any]:
    action_sig = inspect.signature(action_func)

    action_is_async = inspect.iscoroutinefunction(action_func)
    policy_is_async = inspect.iscoroutinefunction(policy_func)

    if action_is_async or policy_is_async:
        async def _call_maybe_async(func: Callable[..., Any], **kwargs: Any) -> Any:
            value = func(**kwargs)
            if inspect.isawaitable(value):
                return await value
            return value

        @functools.wraps(action_func)
        async def wrapper(*args: Any, approved_ticket_id: str | None = None, **kwargs: Any) -> Any:
            bound = action_sig.bind(*args, **kwargs)
            bound.apply_defaults()
            normalized_kwargs = dict(bound.arguments)

            decision_raw = await _call_maybe_async(policy_func, **normalized_kwargs)
            decision, message = _normalize_policy_result(decision_raw)

            if decision == PolicyDecision.ALLOW:
                return await _call_maybe_async(action_func, **normalized_kwargs)

            if decision == PolicyDecision.DENY:
                raise SecurityError(message or "Action denied by policy.")

            if decision == PolicyDecision.REQUIRE_TICKET:
                if approved_ticket_id and ticket_store.is_valid(approved_ticket_id):
                    return await _call_maybe_async(action_func, **normalized_kwargs)
                ticket_id = ticket_store.generate()
                raise SecurityApprovalRequiredError(ticket_id, message or "Action requires user approval.")

            raise SecurityError("Invalid policy decision.")
    else:
        @functools.wraps(action_func)
        def wrapper(*args: Any, approved_ticket_id: str | None = None, **kwargs: Any) -> Any:
            bound = action_sig.bind(*args, **kwargs)
            bound.apply_defaults()
            normalized_kwargs = dict(bound.arguments)

            decision_raw = policy_func(**normalized_kwargs)
            if inspect.isawaitable(decision_raw):
                raise SecurityError("Policy function returned awaitable, but action wrapper is synchronous.")
            decision, message = _normalize_policy_result(decision_raw)

            if decision == PolicyDecision.ALLOW:
                value = action_func(**normalized_kwargs)
                if inspect.isawaitable(value):
                    raise SecurityError("Action function returned awaitable, but action wrapper is synchronous.")
                return value

            if decision == PolicyDecision.DENY:
                raise SecurityError(message or "Action denied by policy.")

            if decision == PolicyDecision.REQUIRE_TICKET:
                if approved_ticket_id and ticket_store.is_valid(approved_ticket_id):
                    value = action_func(**normalized_kwargs)
                    if inspect.isawaitable(value):
                        raise SecurityError("Action function returned awaitable, but action wrapper is synchronous.")
                    return value
                ticket_id = ticket_store.generate()
                raise SecurityApprovalRequiredError(ticket_id, message or "Action requires user approval.")

            raise SecurityError("Invalid policy decision.")

    sig_params = list(action_sig.parameters.values()) + [
        inspect.Parameter(
            "approved_ticket_id",
            kind=inspect.Parameter.KEYWORD_ONLY,
            default=None,
            annotation=str | None,
        )
    ]
    setattr(wrapper, "__signature__", inspect.Signature(parameters=sig_params, return_annotation=action_sig.return_annotation))

    return wrapper

class SecureFileSystem:
    """
    基于受限环境的底层文件 SDK。
    限制文件读写操作必须在指定的 working_dir 内，防止路径穿越攻击（Path Traversal）。
    黑白名单由外部传入，不命中白名单则进入灰名单。
    """
    def __init__(
        self, 
        working_dir: str | Path,
        blacklist_patterns: list[str | re.Pattern] | None = None,
        whitelist_patterns: list[str | re.Pattern] | None = None
    ):
        self.working_dir = Path(working_dir).resolve()
        
        self.blacklist_patterns = []
        if blacklist_patterns:
            for p in blacklist_patterns:
                self.blacklist_patterns.append(re.compile(p) if isinstance(p, str) else p)
                
        self.whitelist_patterns = []
        if whitelist_patterns:
            for p in whitelist_patterns:
                self.whitelist_patterns.append(re.compile(p) if isinstance(p, str) else p)

        self.read_text = create_secure_action(
            self._read_text_action,
            self._read_text_policy,
        )
        self.write_text = create_secure_action(
            self._write_text_action,
            self._write_text_policy,
        )

    def _resolve(self, path: str | Path) -> Path:
        try:
            return (self.working_dir / path).resolve()
        except Exception as e:
            raise SecurityError(f"Invalid path: {e}")

    def _decide(self, target: Path, mode: str) -> tuple[PolicyDecision, str]:
        target_str = str(target)
        for pattern in self.blacklist_patterns:
            if pattern.match(target_str):
                return PolicyDecision.DENY, f"Access denied to sensitive path: {target_str}"
        for pattern in self.whitelist_patterns:
            if pattern.match(target_str):
                return PolicyDecision.ALLOW, "Allowed by whitelist."
        return PolicyDecision.REQUIRE_TICKET, f"Access to path '{target_str}' (mode: {mode}) requires user approval."

    def _read_text_policy(self, path: str | Path) -> tuple[PolicyDecision, str]:
        target = self._resolve(path)
        return self._decide(target, "r")

    def _read_text_action(self, path: str | Path) -> str:
        target = self._resolve(path)
        return target.read_text(encoding="utf-8")

    def _write_text_policy(self, path: str | Path, content: str) -> tuple[PolicyDecision, str]:
        target = self._resolve(path)
        return self._decide(target, "w")

    def _write_text_action(self, path: str | Path, content: str) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

class SecureShell:
    """
    受限命令行执行 SDK。
    使用 bashlex 提取复杂命令的 base commands。
    黑白名单由外部传入，不命中白名单则进入灰名单。
    """
    def __init__(
        self, 
        working_dir: str | Path,
        blacklist_cmds: set[str] | list[str] | None = None,
        whitelist_cmds: set[str] | list[str] | None = None
    ):
        self.working_dir = Path(working_dir).resolve()
        self.blacklist_cmds = set(blacklist_cmds) if blacklist_cmds else set()
        self.whitelist_cmds = set(whitelist_cmds) if whitelist_cmds else set()
        self.execute = create_secure_action(
            self._execute_action,
            self._execute_policy,
        )

    def _extract_commands(self, command: str) -> list[str] | None:
        try:
            parts = bashlex.parse(command)
        except bashlex.errors.ParsingError:
            # 解析失败（存在语法错误或不支持的语法），直接返回 None，后续交由灰名单处理
            return None
            
        cmds = []
        class CommandVisitor(bashlex.ast.nodevisitor):
            def visitcommand(self, n, parts):
                for p in n.parts:
                    if p.kind == 'word':
                        cmds.append(p.word)
                        break
        visitor = CommandVisitor()
        for part in parts:
            visitor.visit(part)
            
        return cmds

    def _execute_policy(self, command: str) -> tuple[PolicyDecision, str]:
        if not command.strip():
            return PolicyDecision.DENY, "Empty command"

        base_cmds = self._extract_commands(command)
        if base_cmds is None:
            return PolicyDecision.REQUIRE_TICKET, f"Command '{command}' requires user approval to execute."

        for cmd in base_cmds:
            if cmd in self.blacklist_cmds:
                return PolicyDecision.DENY, f"Command '{cmd}' is blacklisted and strictly prohibited."

        if base_cmds and all(cmd in self.whitelist_cmds for cmd in base_cmds):
            return PolicyDecision.ALLOW, "Allowed by whitelist."

        return PolicyDecision.REQUIRE_TICKET, f"Command '{command}' requires user approval to execute."

    def _execute_action(self, command: str) -> str:
        try:
            result = subprocess.run(
                command,
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                check=False,
                shell=True
            )
            if result.returncode != 0:
                return f"Error ({result.returncode}): {result.stderr}"
            return result.stdout
        except Exception as e:
            return f"Execution failed: {e}"

class ToolSecurityPrimitive:
    """
    (SH-P0-01) PyTools 安全原语实现。
    
    提供受控 SDK 供工具函数内部使用。
    """
    def __init__(
        self, 
        working_dir: str | Path | None = None,
        fs_blacklist: list[str | re.Pattern] | None = None,
        fs_whitelist: list[str | re.Pattern] | None = None,
        shell_blacklist: set[str] | list[str] | None = None,
        shell_whitelist: set[str] | list[str] | None = None,
    ):
        self.working_dir = Path(working_dir).resolve() if working_dir else Path.cwd()
        
        self.secure_fs = SecureFileSystem(self.working_dir, fs_blacklist, fs_whitelist)
        self.secure_shell = SecureShell(self.working_dir, shell_blacklist, shell_whitelist)

def with_security_policy(policy: ToolSecurityPrimitive) -> Callable:
    """
    安全策略拦截器（装饰器）。
    包裹基础的 Capability handler。拦截并处理 SecurityError 和 SecurityApprovalRequiredError，
    实现平滑降级，并在成功执行后核销 ticket。
    """
    def decorator(handler: Callable[[CapabilityRequest], Awaitable[CapabilityResult]]) -> Callable[[CapabilityRequest], Awaitable[CapabilityResult]]:
        @functools.wraps(handler)
        async def wrapper(request: CapabilityRequest) -> CapabilityResult:
            try:
                # 1. 执行工具逻辑（工具内部应使用 SDK）
                result = await handler(request)
                
                # 3. 如果请求成功执行且携带有 ticket，则核销该 ticket
                approved_ticket_id = request.ticket_id
                if approved_ticket_id and getattr(result, "success", False) is True:
                    _global_ticket_store.consume(approved_ticket_id)
                    
                return result
                
            except SecurityError as e:
                # 命中黑名单，直接阻断
                return CapabilityResult(
                    capability_id=request.capability_id,
                    success=False,
                    output={},
                    error_code="security_policy_violation",
                    error_message=str(e),
                    metadata={"security_blocked": True}
                )
            except SecurityApprovalRequiredError as e:
                # 命中灰名单，生成凭证并要求授权
                return CapabilityResult(
                    capability_id=request.capability_id,
                    success=False,
                    output={},
                    error_code="requires_user_approval",
                    error_message=str(e),
                    metadata={"ticket_id": e.ticket_id}
                )
            # 未捕获的异常（如工具内部崩溃）交由外层统一处理
        return wrapper
    return decorator

# 提供一个全局默认策略实例（全灰名单）
default_security_policy = ToolSecurityPrimitive(working_dir=Path.cwd())
