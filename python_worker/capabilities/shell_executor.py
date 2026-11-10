"""Capability: Execute shell commands in a sandboxed workspace context.

Provides safe shell execution with timeout, environment isolation, and structured output.
Designed for operations like pip install, npm install, git commands, environment checks, etc.
"""

import os
import subprocess
import time
from dataclasses import dataclass, field


DANGEROUS_COMMANDS = frozenset({
    "rm -rf /", "rm -rf ~", "rm -rf .", "dd if=", "mkfs",
    ":(){ :|:& };:", "format c:", "format d:",
    "del /f /s /q c:\\", "deltree /y c:\\",
})

BLOCKED_PATTERNS = [
    "rm -rf /",
    "rm -rf ~",
    "rm -rf .",
    "chmod 777 /",
    "> /dev/sda",
    "mkfs.",
]


@dataclass
class ShellResult:
    success: bool = False
    command: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    elapsed_ms: int = 0
    blocked: bool = False
    timeout: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "command": self.command,
            "stdout": self.stdout[:5000],
            "stderr": self.stderr[:2000],
            "exit_code": self.exit_code,
            "elapsed_ms": self.elapsed_ms,
            "blocked": self.blocked,
            "timeout": self.timeout,
            "error": self.error,
        }

    def format_for_user(self) -> str:
        if self.blocked:
            return f"## 命令已被阻止\n\n`{self.command}` 包含危险操作，已自动阻止执行。"

        lines = [f"## 命令执行{'成功' if self.success else '失败'}", ""]

        if self.error and not self.stdout and not self.stderr:
            lines.append(f"**错误:** {self.error}")
            return "\n".join(lines)

        lines.append(f"**命令:** `{self.command}`")
        lines.append(f"**退出码:** {self.exit_code}")
        lines.append(f"**耗时:** {self.elapsed_ms}ms")

        if self.timeout:
            lines.append("**警告:** 命令执行超时")
            return "\n".join(lines)

        if self.stdout.strip():
            lines.append("")
            lines.append("### 标准输出")
            lines.append("```")
            lines.append(self.stdout[:3000])
            if len(self.stdout) > 3000:
                lines.append(f"... (输出过长，已截断，共 {len(self.stdout)} 字符)")
            lines.append("```")

        if self.stderr.strip():
            lines.append("")
            lines.append("### 标准错误")
            lines.append("```")
            lines.append(self.stderr[:2000])
            lines.append("```")

        return "\n".join(lines)


def _is_dangerous(command: str) -> tuple:
    """Check if a command is potentially dangerous. Returns (is_dangerous, reason)."""
    cmd_lower = command.lower().strip()

    if cmd_lower in DANGEROUS_COMMANDS:
        return True, "命令在黑名单中"

    for pattern in BLOCKED_PATTERNS:
        if pattern.lower() in cmd_lower:
            if "rm -rf" in cmd_lower and "/tmp" in cmd_lower:
                continue
            return True, f"匹配危险模式: {pattern}"

    if ("curl" in cmd_lower or "wget" in cmd_lower) and "|" in cmd_lower and ("sh" in cmd_lower or "bash" in cmd_lower):
        return True, "curl/wget 通过管道执行 shell — 可能执行远程脚本"

    return False, ""


def run_command(
    command: str,
    cwd: str = None,
    timeout: int = 60,
    env: dict = None,
    shell: bool = True,
    path_guard=None,
) -> ShellResult:
    """Execute a shell command in a sandboxed environment.

    Args:
        command: The shell command string to execute
        cwd: Working directory for the command (default: current directory)
        timeout: Maximum execution time in seconds (default: 60)
        env: Optional environment variable overrides
        shell: Whether to use shell execution (default: True)
        path_guard: Optional PathGuard instance for authorization (Phase 2.3+).
                    If not provided, falls back to basic danger checks only.

    Returns:
        ShellResult with exit code, stdout, stderr, and timing.
    """
    result = ShellResult(command=command)

    dangerous, reason = _is_dangerous(command)
    if dangerous:
        result.blocked = True
        result.error = reason
        result.success = False
        return result

    if path_guard is not None:
        try:
            path_guard.validate_execute(
                cwd=cwd or os.getcwd(),
                command=command,
                env=env,
            )
        except Exception as e:
            result.blocked = True
            result.error = f"PathGuard 拒绝执行: {e}"
            result.success = False
            return result

    process_env = os.environ.copy()
    if env:
        process_env.update(env)

    t0 = time.time()
    try:
        proc = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
            env=process_env,
        )
        result.exit_code = proc.returncode
        result.stdout = proc.stdout or ""
        result.stderr = proc.stderr or ""
        result.success = proc.returncode == 0
        result.elapsed_ms = int((time.time() - t0) * 1000)

    except subprocess.TimeoutExpired:
        result.timeout = True
        result.error = f"命令执行超时 ({timeout}s)"
        result.elapsed_ms = int((time.time() - t0) * 1000)

    except FileNotFoundError:
        result.error = f"命令未找到: {command.split()[0] if command else '未知'}"
        result.exit_code = 127

    except PermissionError as e:
        result.error = f"权限不足: {e}"
        result.exit_code = 126

    except Exception as e:
        result.error = str(e)
        result.exit_code = -1

    return result