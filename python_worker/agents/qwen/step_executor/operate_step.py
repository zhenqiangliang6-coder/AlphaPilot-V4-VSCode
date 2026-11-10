"""Execute system operations (git upload, code counting, shell commands) instead of generating tools."""

import os
import sys
from ..qwen_api import call_qwen_with_persona
from ....worker_config import create_event, stream_chunk, stream_end, stream_start


def _detect_operation_type(user_request: str) -> str:
    """Classify the operation request into a specific operation type."""
    request_lower = (user_request or "").lower().strip()

    if any(kw in request_lower for kw in ("上传", "推送", "push", "github", "git")):
        if any(kw in request_lower for kw in ("代码行", "行数", "count", "line", "cloc")):
            return "code_counter"
        return "git_upload"

    if any(kw in request_lower for kw in ("代码行", "行数", "count", "line", "cloc",
                                             "多少行", "统计", "代码量")):
        return "code_counter"

    if any(kw in request_lower for kw in ("运行", "执行", "run", "exec", "脚本",
                                             "命令", "shell", "bash", "pip", "npm")):
        return "shell_command"

    if any(kw in request_lower for kw in ("环境", "检测", "检查", "env", "版本")):
        return "env_check"

    return "generic_operation"


def _execute_git_upload(step, context, events, task_id, workspace_path):
    """Execute GitHub upload with SSH detection, retry, and China network adaptation."""
    from ....capabilities.git_upload import (
        GitUploadResult,
        upload_to_github,
    )

    if not workspace_path or not os.path.isdir(workspace_path):
        step["output"] = {"text": "上传失败：未找到有效的工作区路径。请先在本地打开一个项目文件夹。"}
        return

    if task_id:
        stream_start(task_id, "正在检测 Git/SSH 环境并上传...", phase="operate")

    result = upload_to_github(workspace_path, progress_callback=lambda msg: (
        stream_chunk(task_id, msg, phase="operate", channel="tool")
        if task_id else None
    ))

    if task_id:
        stream_end(task_id)

    step["output"] = {"text": result.format_for_user()}
    context.setdefault("intermediate_results", []).append({
        "type": "operate",
        "operation": "git_upload",
        "result": result.to_dict(),
    })


def _execute_code_counter(step, context, events, task_id, workspace_path):
    """Count code lines directly and return the result as text."""
    from ....capabilities.code_analyzer import (
        count_lines,
        CodeStats,
    )

    if not workspace_path or not os.path.isdir(workspace_path):
        step["output"] = {"text": "统计失败：未找到有效的工作区路径。"}
        return

    if task_id:
        stream_start(task_id, "正在统计代码行数...", phase="operate")

    stats = count_lines(workspace_path)

    if task_id:
        stream_end(task_id)

    step["output"] = {"text": stats.format_for_user()}
    context.setdefault("intermediate_results", []).append({
        "type": "operate",
        "operation": "code_counter",
        "result": stats.to_dict(),
    })


def _execute_shell_command(step, context, events, task_id, workspace_path):
    """Execute a shell command in sandbox and return stdout/stderr."""
    from ....capabilities.shell_executor import run_command, ShellResult

    user_request = context.get("meta", {}).get("user_request", "")
    cmd = _extract_command(user_request)

    if not cmd:
        step["output"] = {"text": "未能从请求中解析出可执行的命令。请明确指定要运行的命令。"}
        return

    if task_id:
        stream_start(task_id, f"正在执行命令: {cmd}", phase="operate")

    result = run_command(cmd, cwd=workspace_path, timeout=60)

    if task_id:
        stream_end(task_id)

    step["output"] = {"text": result.format_for_user()}
    context.setdefault("intermediate_results", []).append({
        "type": "operate",
        "operation": "shell_command",
        "command": cmd,
        "result": result.to_dict(),
    })


def _execute_env_check(step, context, events, task_id, workspace_path):
    """Check environment (Python, Node, Git, SSH) and report findings."""
    from ....capabilities.shell_executor import run_command, ShellResult

    checks = {}

    if workspace_path:
        checks["venv"] = os.path.isdir(os.path.join(workspace_path, ".venv"))
        checks["node_modules"] = os.path.isdir(os.path.join(workspace_path, "node_modules"))

    git_result = run_command("git --version", cwd=workspace_path, timeout=10)
    checks["git"] = {
        "installed": git_result.success,
        "version": git_result.stdout.strip() if git_result.success else "未安装"
    }

    ssh_result = run_command("ssh -T git@github.com 2>&1", cwd=workspace_path, timeout=10)
    checks["ssh"] = {
        "key_exists": os.path.exists(os.path.expanduser("~/.ssh/id_rsa"))
                      or os.path.exists(os.path.expanduser("~/.ssh/id_ed25519")),
        "github_connected": "successfully authenticated" in ssh_result.stderr.lower()
                            or "successfully authenticated" in ssh_result.stdout.lower(),
    }

    lines = [
        "## 环境检测报告",
        "",
        f"| 项目 | 状态 | 详情 |",
        f"|------|------|------|",
    ]

    venv_status = "已存在" if checks["venv"] else "未创建"
    lines.append(f"| Python .venv | {'✅' if checks['venv'] else '⚠️'} | {venv_status} |")

    nm_status = "已存在" if checks["node_modules"] else "未安装"
    lines.append(f"| Node .node_modules | {'✅' if checks['node_modules'] else '⚠️'} | {nm_status} |")

    lines.append(f"| Git | {'✅' if checks['git']['installed'] else '❌'} | {checks['git']['version']} |")

    s = checks["ssh"]
    if s["github_connected"]:
        lines.append("| SSH GitHub | ✅ | 已认证 |")
    elif s["key_exists"]:
        lines.append("| SSH GitHub | ⚠️ | 密钥存在但未连接，请确认公钥已添加到GitHub |")
    else:
        lines.append("| SSH GitHub | ❌ | 未配置SSH密钥，请运行 ssh-keygen 生成 |")

    step["output"] = {"text": "\n".join(lines)}
    context.setdefault("intermediate_results", []).append({
        "type": "operate",
        "operation": "env_check",
        "checks": checks,
    })


def _extract_command(user_request: str) -> str:
    """Extract the shell command from the user's natural language request."""
    import re

    for pattern in [
        r"`([^`]+)`",
        r"运行\s*(.{4,})$",
        r"执行\s*(.{4,})$",
        r"run\s+(.{4,})$",
        r"exec\s+(.{4,})$",
    ]:
        m = re.search(pattern, user_request, re.IGNORECASE)
        if m:
            cmd = m.group(1).strip()
            if len(cmd) > 3:
                return cmd

    return ""


def run_operate_step(step, context, events, task_id=None):
    """Main entry point for the operate step — dispatches to specific operation handlers."""
    meta = context.get("meta", {})
    user_request = meta.get("user_request", "")
    workspace_path = (
        (meta.get("workspace_scan") or {}).get("root")
        or meta.get("workspace_path")
        or os.getcwd()
    )

    op_type = meta.get("_operation_type") or _detect_operation_type(user_request)
    meta["_operation_type"] = op_type

    print(f"[operate_step] 操作类型: {op_type} | workspace: {workspace_path}")

    handlers = {
        "git_upload": _execute_git_upload,
        "code_counter": _execute_code_counter,
        "shell_command": _execute_shell_command,
        "env_check": _execute_env_check,
        "generic_operation": _execute_env_check,
    }

    handler = handlers.get(op_type, _execute_env_check)
    handler(step, context, events, task_id, workspace_path)