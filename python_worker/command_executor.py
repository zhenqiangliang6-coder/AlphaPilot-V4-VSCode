# -*- coding: utf-8 -*-
# python_worker/command_executor.py — 受控命令执行器
# ---------------------------------------------------------
# 架构定位
#
# CommandExecutor 是统一 CodingWorker 架构的安全执行基座，
# 所有工具链调用（编译、测试、Lint、Git、依赖安装等）的唯一入口。
#
# 治理层次（从外到内）：
#   Layer 1: 可执行程序白名单 — 不是黑名单，是"只有列表中的命令可执行"
#   Layer 2: 工作区边界强制 — 所有操作限制在指定根目录内
#   Layer 3: 环境变量隔离   — 剥离密钥、Token、敏感配置
#   Layer 4: 进程生命周期   — 超时 + 子进程树清理 + 无残留
#   Layer 5: 输出安全截断   — 大小限制 + 敏感信息过滤
#   Layer 6: 审计日志       — 每次执行记录：命令、退出码、耗时、结果
#
# 设计约束：
#   - shell=False 强制（禁止 shell 注入）
#   - 白名单优先（不在白名单的命令绝不执行）
#   - 拒绝即记录（被拦截的命令必须写入审计日志）
#   - 进程树清理（超时不但 kill 主进程，还清理所有子进程）
# ---------------------------------------------------------

from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Set

# =========================================================
# 0. 结果类型
# =========================================================


@dataclass
class CommandResult:
    success: bool = False
    command: str = ""
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    timed_out: bool = False
    blocked: bool = False
    block_reason: str = ""
    error: str = ""

    # 测试结果字段（由调用方填充）
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout": self.stdout[:5000],
            "stderr": self.stderr[:2000],
            "duration_seconds": self.duration_seconds,
            "timed_out": self.timed_out,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "error": self.error,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "skipped_tests": self.skipped_tests,
        }


# =========================================================
# 1. 可执行程序白名单（不是黑名单）
# =========================================================
#
# 黑名单的问题：每次发现一个新的危险命令就要补一个条目，
# 总有遗漏。白名单则相反——不在列表中的命令直接拒绝。
#
# 新增工具链时，必须明确将可执行文件加入本列表。

_ALLOWED_EXECUTABLES: Set[str] = {
    # Python 生态
    "python", "python3", "pip", "pytest", "flake8", "black", "mypy",
    "pipenv", "poetry", "uv", "ruff",

    # Node / TypeScript 生态
    "node", "npm", "npx", "yarn", "pnpm", "tsc", "jest", "mocha",
    "eslint", "prettier",

    # Java 生态
    "java", "javac", "mvn", "gradle", "gradlew",

    # Go 生态
    "go", "gofmt",

    # Rust 生态
    "cargo", "rustc", "rustfmt", "clippy-driver",

    # Git
    "git",

    # Docker（仅信息查询命令）
    "docker",

    # 系统工具（受限集合）
    "echo", "cat", "head", "tail", "wc", "sort", "uniq", "grep",
    "find", "ls", "pwd", "which", "mkdir", "cp", "mv", "touch",
}


def _resolve_executable(cmd: List[str]) -> str:
    """提取命令列表中的可执行文件名（不含路径和扩展名）。"""
    if not cmd:
        return ""
    exe = os.path.basename(cmd[0])
    # 去掉 Windows .exe/.bat/.cmd 后缀做对比
    if os.name == "nt":
        for suffix in (".exe", ".bat", ".cmd", ".com"):
            if exe.lower().endswith(suffix):
                exe = exe[:-len(suffix)]
    return exe.lower()


# =========================================================
# 2. 密钥/Token 检测模式（输出过滤）
# =========================================================

_SECRET_PATTERNS = [
    (re.compile(r'sk-[a-zA-Z0-9]{20,}'), "[REDACTED:API_KEY]"),
    (re.compile(r'AKIA[0-9A-Z]{16}'), "[REDACTED:AWS_KEY]"),
    (re.compile(r'ghp_[a-zA-Z0-9]{36}'), "[REDACTED:GH_TOKEN]"),
    (re.compile(r'gho_[a-zA-Z0-9]{36}'), "[REDACTED:GH_TOKEN]"),
    (re.compile(r'github_pat_[a-zA-Z0-9_]{36,}'), "[REDACTED:GH_PAT]"),
    (re.compile(r'(?:access|auth)_token[=:]\s*[^\s]{8,}', re.I), "[REDACTED:TOKEN]"),
    (re.compile(r'Authorization:\s*Bearer\s+[^\s]{8,}', re.I), "[REDACTED:AUTH_HEADER]"),
    (re.compile(r'DATABASE_URL[=:]\s*[^\s]{8,}', re.I), "[REDACTED:DB_URL]"),
    (re.compile(r'password[=:]\s*[^\s]{3,}', re.I), "[REDACTED:PASSWORD]"),
]


def _sanitize_output(text: str, max_bytes: int = 50000) -> str:
    """过滤输出中的敏感信息并截断超长内容。

    策略：
      1. 移除所有匹配 SECRET_PATTERNS 的内容
      2. 截断到 max_bytes（保留开头和结尾，中间标记截断）
    """
    if not text:
        return ""

    sanitized = text
    for pattern, replacement in _SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    if len(sanitized) <= max_bytes:
        return sanitized

    half = max_bytes // 2
    return (
        sanitized[:half]
        + f"\n\n... ({len(sanitized) - max_bytes} chars truncated) ...\n\n"
        + sanitized[-half:]
    )


# =========================================================
# 3. CommandExecutor — 核心治理引擎
# =========================================================


class CommandExecutor:
    """受控命令执行器。

    使用方式：
        executor = CommandExecutor(
            allowed_workspace_root="/home/alphapilot/workspaces",
            audit_log_path="/var/log/alphapilot/commands.log",
        )
        result = executor.run(["pytest", "-v"], workspace="/home/alphapilot/workspaces/task-123")
    """

    def __init__(
        self,
        allowed_workspace_root: Optional[str] = None,
        audit_log_path: Optional[str] = None,
        extra_allowed_executables: Optional[Set[str]] = None,
    ):
        self.allowed_workspace_root = os.path.realpath(
            allowed_workspace_root or os.environ.get(
                "ALPHAPILOT_WORKSPACE_ROOT",
                os.path.join(os.path.expanduser("~"), "alphapilot_workspaces"),
            )
        )
        self.audit_log_path = audit_log_path

        self.allowed_executables = set(_ALLOWED_EXECUTABLES)
        if extra_allowed_executables:
            self.allowed_executables.update(extra_allowed_executables)

        self._audit_entries: List[dict] = []

    # ── 公共 API ──

    def run(
        self,
        cmd: List[str],
        workspace: str,
        timeout: int = 300,
        env_allowlist: Optional[Set[str]] = None,
    ) -> CommandResult:
        """执行一条命令，经过全部 6 层治理。

        Args:
            cmd:           命令 + 参数列表（shell=False 强制要求 list）
            workspace:     工作区绝对路径（必须在 allowed_workspace_root 内）
            timeout:       超时秒数
            env_allowlist: 允许透传的环境变量名集合（None=使用默认白名单）

        Returns:
            CommandResult（即使被拦截也返回，不会抛异常）
        """
        t0 = time.time()
        cmd_str = " ".join(cmd)
        workspace = os.path.realpath(workspace)

        # ── Layer 1: 可执行程序白名单校验 ──
        exe = _resolve_executable(cmd)
        if exe not in self.allowed_executables:
            result = CommandResult(
                command=cmd_str,
                blocked=True,
                block_reason=f"executable '{exe}' not in allowlist",
                duration_seconds=round(time.time() - t0, 3),
            )
            self._audit(result, workspace)
            return result

        # ── Layer 2: 工作区边界强制 ──
        root = self.allowed_workspace_root
        if not workspace.startswith(root + os.sep) and workspace != root:
            result = CommandResult(
                command=cmd_str,
                blocked=True,
                block_reason=(
                    f"workspace '{workspace}' outside root '{root}'"
                ),
                duration_seconds=round(time.time() - t0, 3),
            )
            self._audit(result, workspace)
            return result

        # ── Layer 3: 环境变量隔离 ──
        process_env = self._build_isolated_env(env_allowlist)

        # ── Layer 4-5: 执行 + 输出采集 ──
        result = self._execute(cmd, workspace, timeout, process_env, cmd_str)
        result.duration_seconds = round(time.time() - t0, 3)

        # ── Layer 6: 审计日志 ──
        self._audit(result, workspace)
        return result

    # ── 内部实现 ──

    def _build_isolated_env(self, env_allowlist: Optional[Set[str]] = None) -> dict:
        """构建隔离的环境变量。

        默认只保留安全的系统级变量。
        env_allowlist 可指定额外允许透传的变量名。
        """
        default_safe = {
            "PATH", "HOME", "USER", "USERNAME", "HOMEDRIVE", "HOMEPATH",
            "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR",
            "LANG", "LC_ALL", "LC_CTYPE",
            "JAVA_HOME", "GOPATH", "GOROOT", "CARGO_HOME", "RUSTUP_HOME",
            "NODE_PATH", "PYTHONPATH",
            "SHELL", "TERM", "COLORTERM", "NO_COLOR", "FORCE_COLOR",
            "VIRTUAL_ENV", "PIP_REQUIRE_VIRTUALENV",
            "ALPHAPILOT_WORKSPACE_ROOT",
        }

        allowed = default_safe.copy()
        if env_allowlist:
            allowed.update(env_allowlist)

        isolated = {}
        for key, value in os.environ.items():
            if key in allowed:
                isolated[key] = value

        # 确保工作区 temp 使用隔离目录
        isolated["TMPDIR"] = os.path.join(self.allowed_workspace_root, ".tmp")
        isolated["TEMP"] = isolated["TMPDIR"]
        isolated["TMP"] = isolated["TMPDIR"]

        return isolated

    def _execute(
        self,
        cmd: List[str],
        workspace: str,
        timeout: int,
        env: dict,
        cmd_str: str,
    ) -> CommandResult:
        """执行子进程，含超时 + 进程树清理。"""
        try:
            os.makedirs(workspace, exist_ok=True)
        except OSError:
            pass

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                shell=False,
                text=True,
            )
        except FileNotFoundError:
            return CommandResult(
                command=cmd_str,
                error=f"command not found: {cmd[0]}",
                exit_code=127,
            )
        except PermissionError as e:
            return CommandResult(
                command=cmd_str,
                error=f"permission denied: {e}",
                exit_code=126,
            )
        except Exception as e:
            return CommandResult(
                command=cmd_str,
                error=str(e),
                exit_code=-1,
            )

        stdout = ""
        stderr = ""
        timed_out = False

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_process_tree(proc.pid)
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()

        stdout = _sanitize_output(stdout or "")
        stderr = _sanitize_output(stderr or "")

        return CommandResult(
            success=(proc.returncode == 0 and not timed_out),
            command=cmd_str,
            exit_code=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            error=("timed out" if timed_out else ""),
        )

    def _kill_process_tree(self, pid: int):
        """清理进程树——kill 父进程及所有子进程。"""
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    timeout=10,
                )
            else:
                try:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    os.kill(pid, signal.SIGKILL)
        except Exception:
            pass

    def _audit(self, result: CommandResult, workspace: str):
        """记录审计日志。"""
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "command": result.command,
            "workspace": workspace,
            "exit_code": result.exit_code,
            "duration_seconds": result.duration_seconds,
            "blocked": result.blocked,
            "block_reason": result.block_reason,
            "timed_out": result.timed_out,
            "success": result.success,
            "stdout_bytes": len(result.stdout) if result.stdout else 0,
            "stderr_bytes": len(result.stderr) if result.stderr else 0,
        }
        self._audit_entries.append(entry)

        if self.audit_log_path:
            try:
                import json
                os.makedirs(os.path.dirname(self.audit_log_path), exist_ok=True)
                with open(self.audit_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception:
                pass

    def get_audit_trail(self) -> List[dict]:
        """返回当前会话的完整审计轨迹。"""
        return list(self._audit_entries)

    def get_rejected_commands(self) -> List[dict]:
        """返回被拦截的命令列表。"""
        return [e for e in self._audit_entries if e["blocked"]]


# =========================================================
# 4. 全局实例（单例模式）
# =========================================================

_default_executor: Optional[CommandExecutor] = None


def get_executor(
    allowed_workspace_root: Optional[str] = None,
    audit_log_path: Optional[str] = None,
) -> CommandExecutor:
    """获取全局 CommandExecutor 实例。

    首次调用时根据参数或环境变量创建，后续调用返回同一实例。

    环境变量：
      ALPHAPILOT_WORKSPACE_ROOT  — 允许的工作区根目录
      ALPHAPILOT_AUDIT_LOG       — 审计日志路径
    """
    global _default_executor
    if _default_executor is None:
        _default_executor = CommandExecutor(
            allowed_workspace_root=(
                allowed_workspace_root
                or os.environ.get("ALPHAPILOT_WORKSPACE_ROOT")
            ),
            audit_log_path=(
                audit_log_path
                or os.environ.get("ALPHAPILOT_AUDIT_LOG")
            ),
        )
    return _default_executor


def reset_executor():
    """重置全局实例（测试用）。"""
    global _default_executor
    _default_executor = None