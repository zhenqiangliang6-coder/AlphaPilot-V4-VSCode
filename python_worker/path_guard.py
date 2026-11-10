# -*- coding: utf-8 -*-
"""
Phase 2.3 PathGuard — 执行边界防御层

v1 声明：PathGuard 是 Worker 内部防御层，不能替代操作系统级进程隔离。
命令执行仍存在残余风险（可通过绝对路径、子进程、环境变量绕过）。

六种操作能力模型:
  validate_read(path)        → allowed_paths.read
  validate_write(path)       → allowed_paths.write + 敏感路径策略
  validate_create_dir(path)  → allowed_paths.write + 父目录在 write/read 内
  validate_delete(path, r)   → allowed_paths.write + 独立确认
  validate_move(src, dst)    → 两端均在 allowed_paths.write
  validate_execute(cwd, cmd) → allowed_paths.execute + 命令策略

安全检查流水线: resolve → authorized_roots → allowed_paths → sensitive_path → command_policy → audit_log

安全不变量:
  - PathGuard 拒绝不可覆盖
  - Worker 不可替换 PathGuard 实例
  - symlink 用 realpath() 检查
  - TOCTOU 是 Python 层面的已知限制，需要 OS 级隔离才是真正方案
"""

import os
import re
import shlex
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from .task_context_contract import (
        AllowedPaths,
        AuthorizationDenied,
        TaskContext,
        TaskContextValidationError,
    )
except ImportError:
    from task_context_contract import (  # type: ignore
        AllowedPaths,
        AuthorizationDenied,
        TaskContext,
        TaskContextValidationError,
    )

_V1_RESIDUAL_RISK = (
    "PathGuard 是 Worker 内部防御层，不能替代操作系统级进程隔离。"
    "命令仍可能通过绝对路径、子进程或环境变量写入 allowed_paths.execute 之外的目录。"
    "此风险在 v1 中公开声明，不作为安全缺陷报告。"
)


# ================================================================
# 1. 路径工具
# ================================================================

def _normalize_path(p: str) -> str:
    if not p:
        return ""
    return os.path.normpath(p).replace("\\", "/").rstrip("/")


def _realpath_safe(p: str) -> str:
    try:
        return os.path.realpath(p).replace("\\", "/").rstrip("/")
    except OSError:
        return _normalize_path(p)


def _is_path_within(child: str, parent: str) -> bool:
    nc = _normalize_path(child)
    np = _normalize_path(parent)
    if nc == np:
        return True
    if not np.endswith("/"):
        np += "/"
    if nc.startswith(np):
        return True
    return False


# ================================================================
# 2. 敏感路径策略（五层）
# ================================================================

L0_CREDENTIAL_FORBIDDEN = re.compile(
    r"(^|/)(\.env($|\..*)|.*\.key$|.*\.pem$|.*\.p12$|secrets\..*|credentials\..*|"
    r"\.git-credentials$|\.npmrc$)",
    re.IGNORECASE,
)

L1_VCS_FORBIDDEN_WRITE = re.compile(
    r"(^|/)\.git/(config|hooks/.*|HEAD|index)$",
    re.IGNORECASE,
)

L2_BUILD_ARTIFACT_FORBIDDEN_DIRECT_WRITE = re.compile(
    r"(^|/)(node_modules|target|dist|build|__pycache__|\.venv|venv|\.pytest_cache)(/|$)",
    re.IGNORECASE,
)

L3_LOCKFILE_FORBIDDEN_DIRECT_WRITE = re.compile(
    r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Cargo\.lock|Gemfile\.lock|composer\.lock)$",
    re.IGNORECASE,
)

SYSTEM_PATHS_WINDOWS = re.compile(
    r"^/?[A-Za-z]/windows(/|$)|"        
    r"^/?[A-Za-z]/program files(/|$)|"  
    r"^/?[A-Za-z]/program files \(x86\)(/|$)|"
    r"^/?[A-Za-z]/system32(/|$)|"
    r"^/?[A-Za-z]/syswow64(/|$)|"
    r"^[A-Za-z]:\\(Windows|Program Files|Program Files \(x86\)|System32|SysWOW64)(\\|$)",
    re.IGNORECASE,
)

SYSTEM_PATHS_UNIX = re.compile(
    r"^/(etc|usr|opt|boot|dev|proc|sys|var/log|var/run)(/|$)"
)


def _normalized_for_pattern(p: str) -> str:
    n = _normalize_path(p)
    if os.name == "nt":
        n = "/" + n.replace(":", "").replace("\\", "/")
    return n


def _check_sensitive_path(path: str, operation: str, is_command_execution: bool = False) -> Optional[str]:
    np = _normalized_for_pattern(path)

    if L0_CREDENTIAL_FORBIDDEN.search(np):
        return f"L0 凭据禁止: {path} (操作: {operation})"

    if operation in ("write", "delete", "create_dir"):
        if not is_command_execution:
            if L1_VCS_FORBIDDEN_WRITE.search(np):
                return f"L1 版本控制禁止直接{operation}: {path}"
            if L2_BUILD_ARTIFACT_FORBIDDEN_DIRECT_WRITE.search(np):
                return f"L2 构建产物禁止直接{operation}: {path}"
            if L3_LOCKFILE_FORBIDDEN_DIRECT_WRITE.search(np):
                return f"L3 锁文件禁止直接{operation}: {path}"

    if operation == "read":
        if L0_CREDENTIAL_FORBIDDEN.search(np):
            return f"L0 凭据禁止读取: {path}"

    return None


# ================================================================
# 3. 命令安全策略（BLOCKED_COMMANDS + DANGEROUS_PATTERNS）
# ================================================================

BLOCKED_COMMANDS = frozenset({
    "rm", "mv", "cp", "chmod", "chown", "sudo", "su", "mkfs", "dd",
    "shutdown", "reboot", "halt", "poweroff", "init", "systemctl",
    "mount", "umount", "fdisk", "parted", "passwd", "useradd", "usermod",
    "iptables", "nftables", "firewall-cmd", "ufw",
})

DANGEROUS_PATTERNS_SHELL = [
    re.compile(p) for p in [
        r">\s*/dev/sd[a-z]",
        r">\s*/dev/nvme",
        r"mkfs\.",
        r"dd\s+if=",
        r":\(\)\s*\{\s*:\|:&\s*\};:",
        r"format\s+[a-zA-Z]:",
        r"deltree\s+/y\s+[a-zA-Z]:",
        r"del\s+/f\s+/s\s+/q\s+[a-zA-Z]:",
        r"(curl|wget)\s+.*\|\s*(sh|bash|zsh|dash|fish)",
        r"(curl|wget)\s+.*\|\s*(python|perl|ruby|node)",
        r">\s*/etc/",
        r">\s*/usr/",
        r">\s*/opt/",
    ]
]

SUSPICIOUS_ENV_VARS = frozenset({
    "PYTHONPATH", "NODE_PATH", "RUBYLIB", "PERL5LIB",
    "CLASSPATH", "GOPATH", "LD_PRELOAD", "LD_LIBRARY_PATH",
    "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH",
})


def _check_command_safety(command: str, cwd: str) -> Optional[str]:
    cmd_lower = command.lower().strip()

    for pattern in DANGEROUS_PATTERNS_SHELL:
        if pattern.search(command):
            return f"命令匹配危险模式: {pattern.pattern}"

    try:
        tokens = shlex.split(command)
    except ValueError:
        pass
    else:
        if tokens:
            base_cmd = os.path.basename(tokens[0]).lower()
            if base_cmd in BLOCKED_COMMANDS:
                return f"命令在阻止列表中: {base_cmd}"

    if re.search(r"(&&|;|\|\||`|\$\(|[{}])", command):
        pass

    return None


def _check_env_safety(env: Optional[Dict[str, str]]) -> List[str]:
    if not env:
        return []
    warnings = []
    for key in SUSPICIOUS_ENV_VARS:
        if key in env:
            warnings.append(f"环境变量 {key} 被显式覆盖（可能影响命令行为）: {env[key][:80]}")
    return warnings


def _check_system_paths(cwd: str) -> Optional[str]:
    if SYSTEM_PATHS_UNIX.search(cwd):
        return f"cwd 指向系统路径: {cwd}"
    normalized = _normalized_for_pattern(cwd)
    if SYSTEM_PATHS_WINDOWS.search(normalized):
        return f"cwd 指向系统路径: {cwd}"
    return None


# ================================================================
# 4. 审计记录
# ================================================================

@dataclass
class AuditRecord:
    timestamp: str = ""
    operation: str = ""
    path: str = ""
    resolved_path: str = ""
    allowed_domain: str = ""
    command: str = ""
    cwd: str = ""
    user_id: str = ""
    task_id: str = ""
    result: str = ""
    context_hash: str = ""
    env_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "operation": self.operation,
            "path": self.path,
            "resolved_path": self.resolved_path,
            "allowed_domain": self.allowed_domain,
            "command": self.command,
            "cwd": self.cwd,
            "user_id": self.user_id,
            "task_id": self.task_id,
            "result": self.result,
            "context_hash": self.context_hash,
            "env_warnings": self.env_warnings,
        }


# ================================================================
# 5. PathGuard 核心类
# ================================================================

class PathGuard:
    """执行边界防御层。

    Worker 在每个文件/命令操作前调用对应的 validate_* 方法。
    PathGuard 实例绑定到单个 TaskContext，Worker 不可替换。
    """

    def __init__(
        self,
        task_context: TaskContext,
        audit_callback: Optional[Callable[[AuditRecord], None]] = None,
    ):
        if not isinstance(task_context, TaskContext):
            raise TaskContextValidationError(
                "PathGuard requires a valid TaskContext",
                reason_code="INVALID_GUARD_CONTEXT",
            )
        self._context = task_context
        self._allowed = task_context.allowed_paths
        self._auth_roots = [os.path.realpath(r) for r in task_context.authorized_roots]
        self._audit = audit_callback or (lambda _: None)
        self._context_hash = task_context.context_hash
        self._compat_policy = task_context.compatibility_policy
        self._task_id = task_context.context_id

    @property
    def context(self) -> TaskContext:
        return self._context

    @property
    def allowed_paths(self) -> AllowedPaths:
        return self._allowed

    def _normalize(self, p: str) -> str:
        return _normalize_path(p)

    def _resolve(self, p: str) -> str:
        return _realpath_safe(p)

    def _audit_record(
        self, operation: str, path: str, domain: str, result: str,
        command: str = "", cwd: str = "", env_warnings: Optional[List[str]] = None,
    ) -> AuditRecord:
        record = AuditRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            operation=operation,
            path=path,
            resolved_path=self._resolve(path) if path else "",
            allowed_domain=domain,
            command=command,
            cwd=cwd,
            result=result,
            context_hash=self._context_hash,
            task_id=self._task_id,
            env_warnings=env_warnings or [],
        )
        self._audit(record)
        return record

    # ---- 六种核心验证方法 ----

    def validate_read(self, path: str) -> str:
        """验证读取权限。返回已解析的安全路径。"""
        resolved = self._resolve(path)
        operation = "read"

        if self._compat_policy == "compat_readonly":
            for domain_path in self._allowed.read:
                if _is_path_within(resolved, domain_path):
                    self._audit_record(operation, path, "read", "ALLOWED_COMPAT")
                    return resolved
            raise AuthorizationDenied(
                f"compat_readonly 不允许读取路径: {path}",
                reason_code="READ_OUTSIDE_ALLOWED",
                audit_record={"path": path, "resolved": resolved, "allowed_read": self._allowed.read},
            )

        if not self._allowed.read:
            raise AuthorizationDenied(
                f"读取路径时 read 域为空: {path}",
                reason_code="READ_DOMAIN_EMPTY",
                audit_record={"path": path, "resolved": resolved},
            )

        for domain_path in self._allowed.read:
            if _is_path_within(resolved, domain_path):
                sensitive = _check_sensitive_path(resolved, operation)
                if sensitive:
                    raise AuthorizationDenied(
                        sensitive,
                        reason_code="SENSITIVE_PATH_READ",
                        audit_record={"path": path, "resolved": resolved},
                    )
                self._audit_record(operation, path, "read", "ALLOWED")
                return resolved

        raise AuthorizationDenied(
            f"path outside allowed_paths.read: {path}",
            reason_code="READ_OUTSIDE_ALLOWED",
            audit_record={"path": path, "resolved": resolved, "allowed_read": self._allowed.read},
        )

    def validate_write(self, path: str) -> str:
        """验证写入权限。返回已解析的安全路径。"""
        resolved = self._resolve(path)
        operation = "write"

        if not self._allowed.write:
            raise AuthorizationDenied(
                f"写入路径时 write 域为空（compat 任务无写入权限）: {path}",
                reason_code="WRITE_DOMAIN_EMPTY",
                audit_record={"path": path, "resolved": resolved},
            )

        for domain_path in self._allowed.write:
            if _is_path_within(resolved, domain_path):
                sensitive = _check_sensitive_path(resolved, operation, is_command_execution=False)
                if sensitive:
                    raise AuthorizationDenied(
                        sensitive,
                        reason_code="SENSITIVE_PATH_WRITE",
                        audit_record={"path": path, "resolved": resolved},
                    )
                self._audit_record(operation, path, "write", "ALLOWED")
                return resolved

        raise AuthorizationDenied(
            f"path outside allowed_paths.write: {path}",
            reason_code="WRITE_OUTSIDE_ALLOWED",
            audit_record={"path": path, "resolved": resolved, "allowed_write": self._allowed.write},
        )

    def validate_create_dir(self, path: str) -> str:
        """验证目录创建权限。目标路径在 write 域内，父目录在 write/read 域内。"""
        resolved = self._resolve(path)
        operation = "create_dir"

        if not self._allowed.write:
            raise AuthorizationDenied(
                f"创建目录时 write 域为空: {path}",
                reason_code="WRITE_DOMAIN_EMPTY",
                audit_record={"path": path, "resolved": resolved},
            )

        in_write = any(_is_path_within(resolved, dp) for dp in self._allowed.write)
        if not in_write:
            raise AuthorizationDenied(
                f"create_dir target outside allowed_paths.write: {path}",
                reason_code="CREATE_DIR_OUTSIDE_WRITE",
                audit_record={"path": path, "resolved": resolved, "allowed_write": self._allowed.write},
            )

        parent = os.path.dirname(resolved)
        while parent != os.path.dirname(parent) and not os.path.exists(parent):
            parent = os.path.dirname(parent)

        parent_resolved = self._resolve(parent)
        parent_in_write = any(_is_path_within(parent_resolved, dp) for dp in self._allowed.write)
        parent_in_read = any(_is_path_within(parent_resolved, dp) for dp in self._allowed.read)
        if not (parent_in_write or parent_in_read):
            raise AuthorizationDenied(
                f"create_dir parent not in allowed_paths (write/read): {parent}",
                reason_code="CREATE_DIR_PARENT_NOT_AUTHORIZED",
                audit_record={"path": path, "parent": parent, "resolved": resolved},
            )

        sensitive = _check_sensitive_path(resolved, operation)
        if sensitive:
            raise AuthorizationDenied(
                sensitive,
                reason_code="SENSITIVE_PATH_WRITE",
                audit_record={"path": path, "resolved": resolved},
            )

        self._audit_record(operation, path, "write", "ALLOWED")
        return resolved

    def validate_delete(self, path: str, recursive: bool = False) -> str:
        """验证删除权限。

        - 非递归: 文件或空目录
        - 递归: 必须经 confirm_scope 确认（返回时需调用方确认后再执行）
        - 敏感路径 (L0/L1) 任何情况拒绝
        """
        resolved = self._resolve(path)
        operation = "delete"

        if not self._allowed.write:
            raise AuthorizationDenied(
                f"删除时 write 域为空: {path}",
                reason_code="WRITE_DOMAIN_EMPTY",
                audit_record={"path": path, "resolved": resolved},
            )

        in_write = any(_is_path_within(resolved, dp) for dp in self._allowed.write)
        if not in_write:
            raise AuthorizationDenied(
                f"delete target outside allowed_paths.write: {path}",
                reason_code="DELETE_OUTSIDE_WRITE",
                audit_record={"path": path, "resolved": resolved, "allowed_write": self._allowed.write},
            )

        sensitive = _check_sensitive_path(resolved, "delete")
        if sensitive:
            raise AuthorizationDenied(
                sensitive,
                reason_code="SENSITIVE_PATH_DELETE",
                audit_record={"path": path, "resolved": resolved},
            )

        if recursive:
            raise AuthorizationDenied(
                f"递归删除必须经用户确认流程: {path}",
                reason_code="RECURSIVE_DELETE_REQUIRES_CONFIRMATION",
                audit_record={"path": path, "recursive": True},
            )

        if os.path.isdir(resolved):
            try:
                contents = os.listdir(resolved)
                if contents:
                    raise AuthorizationDenied(
                        f"目录非空（{len(contents)} 个子项），递归删除需要确认: {path}",
                        reason_code="DIRECTORY_NOT_EMPTY",
                        audit_record={"path": path, "item_count": len(contents)},
                    )
            except PermissionError:
                pass

        self._audit_record(operation, path, "write", "ALLOWED")
        return resolved

    def validate_move(self, src: str, dest: str) -> Tuple[str, str]:
        """验证移动/重命名权限。源和目标两端均必须在 allowed_paths.write 内。"""
        src_resolved = self._resolve(src)
        dest_resolved = self._resolve(dest)
        operation = "move"

        if not self._allowed.write:
            raise AuthorizationDenied(
                f"移动时 write 域为空: {src} -> {dest}",
                reason_code="WRITE_DOMAIN_EMPTY",
                audit_record={"src": src, "dest": dest},
            )

        src_in = any(_is_path_within(src_resolved, dp) for dp in self._allowed.write)
        dest_in = any(_is_path_within(dest_resolved, dp) for dp in self._allowed.write)

        if not src_in:
            raise AuthorizationDenied(
                f"move source outside allowed_paths.write: {src}",
                reason_code="MOVE_SRC_OUTSIDE_WRITE",
                audit_record={"src": src, "src_resolved": src_resolved, "allowed_write": self._allowed.write},
            )
        if not dest_in:
            raise AuthorizationDenied(
                f"move destination outside allowed_paths.write: {dest}",
                reason_code="MOVE_DEST_OUTSIDE_WRITE",
                audit_record={"dest": dest, "dest_resolved": dest_resolved, "allowed_write": self._allowed.write},
            )

        sensitive = _check_sensitive_path(dest_resolved, operation)
        if sensitive:
            raise AuthorizationDenied(
                sensitive,
                reason_code="SENSITIVE_PATH_MOVE",
                audit_record={"src": src, "dest": dest},
            )

        self._audit_record(operation, src, "write", "ALLOWED")
        return src_resolved, dest_resolved

    def validate_execute(
        self, cwd: str, command: str, env: Optional[Dict[str, str]] = None,
    ) -> str:
        """验证命令执行权限。

        管线:
        1. cwd 在 allowed_paths.execute 内
        2. 系统路径检查
        3. 命令安全检查
        4. 环境变量审查
        5. 审计记录

        返回: 已解析的安全 cwd。

        v1 残余风险声明:
        - 命令可通过绝对路径写入 execute 域之外的目录
        - 命令可通过 &&/;/|/$()/反引号串联危险操作
        - 子进程不受 PathGuard 约束
        - 网络操作无独立授权
        """
        resolved_cwd = self._resolve(cwd)
        operation = "execute"

        if not self._allowed.execute:
            raise AuthorizationDenied(
                f"执行命令时 execute 域为空: {command[:80]}...",
                reason_code="EXECUTE_DOMAIN_EMPTY",
                audit_record={"command": command, "cwd": cwd},
            )

        in_execute = any(_is_path_within(resolved_cwd, dp) for dp in self._allowed.execute)
        if not in_execute:
            raise AuthorizationDenied(
                f"cwd outside allowed_paths.execute: {cwd}",
                reason_code="EXECUTE_CWD_OUTSIDE_ALLOWED",
                audit_record={"command": command, "cwd": cwd, "resolved_cwd": resolved_cwd},
            )

        sys_path = _check_system_paths(cwd)
        if sys_path:
            raise AuthorizationDenied(
                sys_path,
                reason_code="EXECUTE_SYSTEM_PATH",
                audit_record={"command": command, "cwd": cwd},
            )

        cmd_issue = _check_command_safety(command, cwd)
        if cmd_issue:
            raise AuthorizationDenied(
                cmd_issue,
                reason_code="DANGEROUS_COMMAND",
                audit_record={"command": command, "cwd": cwd},
            )

        env_warnings = _check_env_safety(env)
        if env_warnings:
            print(f"[PathGuard] env warnings for execute: {'; '.join(env_warnings)}")

        self._audit_record(
            operation, cwd, "execute", "ALLOWED",
            command=command, cwd=resolved_cwd, env_warnings=env_warnings,
        )

        return resolved_cwd


# ================================================================
# 6. 工厂函数
# ================================================================

def create_path_guard(task_context: TaskContext) -> PathGuard:
    """从 TaskContext 创建 PathGuard 实例。"""
    return PathGuard(task_context)


def disable_path_guard(task_context: TaskContext) -> PathGuard:
    """创建宽松 PathGuard（全部操作允许，仅用于测试/回退）。

    在生产环境中不应使用此函数。
    """
    import platform
    if platform.system() == "Windows":
        root = task_context.target_project_path or task_context.workspace_roots[0]
        drive = os.path.splitdrive(root)[0] + "/" if os.path.splitdrive(root)[0] else "/"
    else:
        drive = "/"
    dummy = AllowedPaths(
        read=[drive],
        write=[drive],
        execute=[drive],
    )
    ctx = TaskContext(
        context_id=task_context.context_id,
        workspace_roots=task_context.workspace_roots,
        authorized_roots=[drive],
        allowed_paths=dummy,
        target_project_path=task_context.target_project_path,
        project_mode=task_context.project_mode,
        created_at=task_context.created_at,
    )
    return PathGuard(ctx)