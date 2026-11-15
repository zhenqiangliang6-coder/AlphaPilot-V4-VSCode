# -*- coding: utf-8 -*-
"""Capability: Install project dependencies (pip install -r / npm install).

确定性能力, 零 LLM 依赖:

1. 探测 workspace 的清单文件 (requirements.txt / Pipfile / pyproject.toml / setup.py / package.json)
2. 确定 Python 解释器 (优先 workspace 下的 .venv, 其次当前进程解释器)
3. 通过 shell_executor 沙箱执行安装命令 (带超时 / 危险检测 / 输出透传)
4. 返回结构化结果

原则:
- 幂等: pip / npm 自带幂等, 重复安装安全
- 安全: 复用 shell_executor 的危险命令检测
- 透明: 完整透传 stdout/stderr, 不声称未发生的操作
"""

import os
import sys
from dataclasses import dataclass
from typing import Callable, Optional

from .shell_executor import run_command


# 支持的清单文件, 按优先级排列 (requirements.txt 优先, 因为最直接)
_MANIFEST_NAMES = (
    ("requirements.txt", "python"),
    ("Pipfile", "python"),
    ("pyproject.toml", "python"),
    ("setup.py", "python"),
    ("package.json", "node"),
)


@dataclass
class DependencyInstallResult:
    success: bool = False
    ecosystem: str = ""          # python / node / unknown
    manifest: str = ""           # 检测到的清单文件相对路径
    python_bin: str = ""         # 使用的 Python 解释器
    command: str = ""            # 实际执行的安装命令
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    elapsed_ms: int = 0
    blocked: bool = False
    timeout: bool = False
    error: str = ""
    note: str = ""               # 未找到清单等提示

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "ecosystem": self.ecosystem,
            "manifest": self.manifest,
            "python_bin": self.python_bin,
            "command": self.command,
            "stdout": self.stdout[:5000],
            "stderr": self.stderr[:2000],
            "exit_code": self.exit_code,
            "elapsed_ms": self.elapsed_ms,
            "blocked": self.blocked,
            "timeout": self.timeout,
            "error": self.error,
            "note": self.note,
        }

    def format_for_user(self) -> str:
        if self.error and not self.command:
            return f"## 依赖安装失败\n\n**错误:** {self.error}"

        if self.note:
            return f"## 依赖安装\n\n⚠️ {self.note}"

        lines = [f"## 依赖安装{'成功' if self.success else '失败'}", ""]
        lines.append(f"**生态:** {self.ecosystem}")
        lines.append(f"**清单文件:** `{self.manifest}`")
        if self.python_bin:
            lines.append(f"**Python 解释器:** `{self.python_bin}`")
        lines.append(f"**命令:** `{self.command}`")
        lines.append(f"**退出码:** {self.exit_code}")
        lines.append(f"**耗时:** {self.elapsed_ms}ms")

        if self.blocked:
            lines.append("\n**警告:** 安装命令被沙箱安全策略阻止。")
        elif self.timeout:
            lines.append("\n**警告:** 安装超时。")
        elif not self.success:
            lines.append("\n**状态:** 安装未成功，请查看错误输出。")

        if self.stdout.strip():
            lines.append("")
            lines.append("### 输出")
            lines.append("```")
            lines.append(self.stdout[:3000])
            if len(self.stdout) > 3000:
                lines.append(f"... (输出过长，已截断，共 {len(self.stdout)} 字符)")
            lines.append("```")

        if self.stderr.strip() and not self.success:
            lines.append("")
            lines.append("### 错误输出")
            lines.append("```")
            lines.append(self.stderr[:2000])
            lines.append("```")

        return "\n".join(lines)


def _detect_manifest(workspace_path: str):
    """返回 (manifest_rel_path, ecosystem) 或 (None, '')."""
    for name, ecosystem in _MANIFEST_NAMES:
        if os.path.isfile(os.path.join(workspace_path, name)):
            return name, ecosystem
    return None, ""


def _find_python_env(workspace_path: str) -> str:
    """定位 Python 解释器: 优先 workspace/.venv, 其次当前进程解释器."""
    candidates = []
    if workspace_path:
        if os.name == "nt":
            candidates.append(os.path.join(workspace_path, ".venv", "Scripts", "python.exe"))
        else:
            candidates.append(os.path.join(workspace_path, ".venv", "bin", "python"))
    candidates.append(sys.executable)
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return sys.executable


def install_dependencies(
    workspace_path: str,
    progress_callback: Optional[Callable[[str], None]] = None,
    timeout: int = 600,
) -> DependencyInstallResult:
    """安装项目依赖.

    Args:
        workspace_path: 项目根目录绝对路径
        progress_callback: 进度回调 (接收一条中文进度信息)
        timeout: 安装命令超时时间 (秒), 默认 600

    Returns:
        DependencyInstallResult (结构化结果)
    """
    result = DependencyInstallResult()

    if not workspace_path or not os.path.isdir(workspace_path):
        result.error = "未找到有效的工作区路径。请先打开一个项目文件夹。"
        return result

    # 1. 探测清单文件
    manifest_rel, ecosystem = _detect_manifest(workspace_path)
    if not manifest_rel:
        result.ecosystem = "unknown"
        result.note = (
            "未在项目根目录找到依赖清单文件（requirements.txt / Pipfile / "
            "pyproject.toml / setup.py / package.json）。"
            "如需安装依赖，请先在项目中提供上述清单之一。"
        )
        return result

    result.ecosystem = ecosystem
    result.manifest = manifest_rel

    # 2. 确定解释器与安装命令
    if ecosystem == "python":
        python_bin = _find_python_env(workspace_path)
        result.python_bin = python_bin
        if manifest_rel == "requirements.txt":
            manifest_abs = os.path.join(workspace_path, manifest_rel)
            cmd = f'"{python_bin}" -m pip install -r "{manifest_abs}"'
        else:
            # pyproject.toml / setup.py / Pipfile → 安装项目本体
            cmd = f'"{python_bin}" -m pip install -e .'
    elif ecosystem == "node":
        cmd = "npm install"
    else:
        result.error = f"不支持的生态: {ecosystem}"
        return result

    result.command = cmd

    if progress_callback:
        progress_callback(f"检测到 {ecosystem} 项目清单 {manifest_rel}，开始安装依赖...")

    # 3. 沙箱执行安装
    shell = run_command(cmd, cwd=workspace_path, timeout=timeout)
    result.exit_code = shell.exit_code
    result.stdout = shell.stdout or ""
    result.stderr = shell.stderr or ""
    result.elapsed_ms = shell.elapsed_ms
    result.blocked = shell.blocked
    result.timeout = shell.timeout
    result.success = shell.success
    if shell.error:
        result.error = shell.error

    if progress_callback:
        if result.success:
            progress_callback("依赖安装完成。")
        else:
            progress_callback("依赖安装未成功，详见输出。")

    return result