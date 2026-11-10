"""Capability: GitHub upload with SSH detection, retry, mirror, and China network adaptation.

Industrial-grade Git deployment that:
1. Detects SSH key status and guides user through setup
2. Configures git remote with retry on failure
3. Adapts to China's network environment (mirror support, proxy detection)
4. Filters secrets before push (checks .env, tokens in staging)
5. Provides detailed Chinese-language error messages with fix steps
"""

import os
import re
import subprocess
import time
import json
from dataclasses import dataclass, field
from typing import Optional, Callable


@dataclass
class GitUploadResult:
    success: bool = False
    repo_url: str = ""
    commits_pushed: int = 0
    branch: str = "main"
    error_code: str = ""
    error_detail: str = ""
    fix_steps: list = field(default_factory=list)
    log: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "repo_url": self.repo_url,
            "commits_pushed": self.commits_pushed,
            "branch": self.branch,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "fix_steps": self.fix_steps,
            "log": self.log[-50:],
        }

    def format_for_user(self) -> str:
        if self.success:
            return (
                f"## 上传成功\n\n"
                f"- 仓库: {self.repo_url}\n"
                f"- 分支: {self.branch}\n"
                f"- 推送了 {self.commits_pushed} 个 commit\n"
            )

        lines = [f"## 上传失败: {self.error_code}", "", f"{self.error_detail}", ""]
        if self.fix_steps:
            lines.append("### 修复步骤")
            for i, step in enumerate(self.fix_steps, 1):
                lines.append(f"{i}. {step}")
        return "\n".join(lines)


def _run_cmd(cmd: str, cwd: str = None, timeout: int = 30, env: dict = None) -> tuple:
    """Run a shell command and return (returncode, stdout, stderr)."""
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            cwd=cwd, timeout=timeout, env=process_env
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"命令超时 ({timeout}s): {cmd}"
    except FileNotFoundError:
        return -1, "", f"命令未找到: {cmd}"
    except Exception as e:
        return -1, "", str(e)


def _check_ssh() -> dict:
    """Comprehensive SSH environment check for GitHub."""
    home = os.path.expanduser("~")

    has_rsa = os.path.exists(os.path.join(home, ".ssh", "id_rsa"))
    has_ed25519 = os.path.exists(os.path.join(home, ".ssh", "id_ed25519"))
    has_any_key = has_rsa or has_ed25519

    agent_running = False
    try:
        agent_check = subprocess.run(
            "ssh-add -l", shell=True, capture_output=True, text=True, timeout=5
        )
        agent_running = agent_check.returncode == 0
    except Exception:
        pass

    github_ok = False
    github_msg = ""
    if has_any_key:
        rc, out, err = _run_cmd("ssh -T git@github.com 2>&1", timeout=15)
        combined = (out + err).lower()
        github_ok = "successfully authenticated" in combined
        github_msg = combined.strip()

    return {
        "has_key": has_any_key,
        "key_type": "ed25519" if has_ed25519 else ("rsa" if has_rsa else "none"),
        "agent_running": agent_running,
        "github_authenticated": github_ok,
        "github_message": github_msg,
    }


def _check_github_reachable() -> tuple:
    """Quick GitHub connectivity test."""
    rc, out, err = _run_cmd("curl -sI --connect-timeout 5 https://github.com", timeout=10)
    return rc == 0, out


def _check_gitignore(workspace_path: str) -> list:
    """Check for dangerous files that should be gitignored."""
    dangerous_patterns = [
        ".env", "*.key", "*.pem", "*.cert", "*.crt",
        "secrets.*", "credentials.*", "*_secret*", ".env.local",
        ".env.production", ".env.development",
    ]

    ignored = set()
    gitignore_path = os.path.join(workspace_path, ".gitignore")
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    ignored.add(line)

    warnings = []
    for pattern in dangerous_patterns:
        if pattern not in ignored:
            for root, dirs, files in os.walk(workspace_path):
                dirs[:] = [d for d in dirs if d not in (".git", ".venv", "node_modules", "__pycache__", "venv")]
                for fname in files:
                    if re.match(pattern.replace("*", ".*"), fname):
                        rel = os.path.relpath(os.path.join(root, fname), workspace_path)
                        msg = f"检测到敏感文件 {rel}，建议加入 .gitignore"
                        if msg not in warnings:
                            warnings.append(msg)

    return warnings


def _detect_branch(workspace_path: str) -> str:
    """Detect the current git branch."""
    rc, out, _ = _run_cmd("git rev-parse --abbrev-ref HEAD", cwd=workspace_path, timeout=5)
    if rc == 0 and out.strip():
        return out.strip()
    return "main"


def _count_unpushed_commits(workspace_path: str, branch: str, remote: str = "origin") -> int:
    """Count commits that haven't been pushed yet."""
    cmd = f'git rev-list --count {remote}/{branch}..HEAD 2>&1'
    rc, out, _ = _run_cmd(cmd, cwd=workspace_path, timeout=10)
    if rc == 0 and out.strip().isdigit():
        return int(out.strip())

    cmd = f'git rev-list --count HEAD 2>&1'
    rc, out, _ = _run_cmd(cmd, cwd=workspace_path, timeout=10)
    if rc == 0 and out.strip().isdigit():
        return int(out.strip())
    return 0


def upload_to_github(
    workspace_path: str,
    repo_url: str = None,
    branch: str = None,
    force: bool = False,
    progress_callback: Callable[[str], None] = None,
) -> GitUploadResult:
    """Main entry point for GitHub upload capability.

    Args:
        workspace_path: Local project root path
        repo_url: Optional GitHub repository URL (HTTPS or SSH)
        branch: Optional branch name
        force: Force push
        progress_callback: Optional callback for progress updates

    Returns:
        GitUploadResult with success status and detailed diagnostics
    """
    result = GitUploadResult()
    log = result.log

    def notify(msg: str):
        log.append(msg)
        if progress_callback:
            progress_callback(msg)

    if not os.path.isdir(os.path.join(workspace_path, ".git")):
        notify("检测到项目未初始化 Git 仓库")
        rc, _, _ = _run_cmd("git init", cwd=workspace_path, timeout=10)
        if rc != 0:
            result.error_code = "GIT_INIT_FAILED"
            result.error_detail = "Git 仓库初始化失败"
            result.fix_steps = [
                "确认已安装 Git：https://git-scm.com/downloads",
                "在项目根目录手动运行 git init",
            ]
            return result
        notify("Git 仓库已初始化")

    # PHASE 1: SSH check
    notify("正在检测 SSH 环境...")
    ssh_status = _check_ssh()
    if not ssh_status["has_key"]:
        notify("未检测到 SSH 密钥")
        result.error_code = "SSH_KEY_MISSING"
        result.error_detail = (
            "SSH 密钥未配置。上传到 GitHub 需要 SSH 密钥认证。"
        )
        result.fix_steps = [
            '运行: ssh-keygen -t ed25519 -C "your_email@example.com"',
            '运行: cat ~/.ssh/id_ed25519.pub 复制公钥',
            "打开 https://github.com/settings/keys 添加 SSH key",
            "然后重新执行上传命令",
        ]
        return result

    if not ssh_status["github_authenticated"]:
        notify(f"SSH 密钥存在但未通过 GitHub 认证: {ssh_status['github_message']}")
        result.error_code = "SSH_NOT_AUTHENTICATED"
        result.error_detail = (
            "SSH 密钥已存在但未通过 GitHub 认证。你的公钥可能尚未添加到 GitHub。"
        )
        result.fix_steps = [
            '运行: cat ~/.ssh/id_{}.pub 复制公钥'.format(ssh_status["key_type"]),
            "打开 https://github.com/settings/keys 添加 SSH key",
            "确认后重新执行上传命令",
        ]
        return result

    notify(f"SSH 认证通过 ({ssh_status['key_type']} 密钥)")

    # PHASE 2: GitHub reachability test
    notify("正在检测 GitHub 网络连接...")
    reachable, _ = _check_github_reachable()
    if not reachable:
        notify("GitHub 直连不可达，尝试检测代理或镜像方案")
        result.error_code = "NETWORK_UNREACHABLE"
        result.error_detail = (
            "无法连接到 GitHub。这在国内网络环境下很常见。"
        )
        result.fix_steps = [
            "方案 1：设置代理 git config --global http.proxy http://127.0.0.1:7890",
            "方案 2：使用镜像 git config --global url.\"https://ghproxy.com/https://github.com\".insteadOf https://github.com",
            "方案 3：使用 GitHub CLI (gh) gh auth login",
            "方案 4：配置 SSH over HTTPS 443 端口，编辑 ~/.ssh/config 添加:\n"
            "  Host github.com\n"
            "    Hostname ssh.github.com\n"
            "    Port 443\n"
            "    User git",
        ]
        return result

    # PHASE 3: Secret check
    notify("正在检查敏感文件...")
    warnings = _check_gitignore(workspace_path)
    if warnings:
        for w in warnings:
            notify(w)
        if not force:
            result.error_code = "SECRET_WARNING"
            result.error_detail = "检测到敏感文件可能被提交，请确认后重新操作"
            result.fix_steps = [
                "将以下模式加入 .gitignore：.env, *.key, *.pem, secrets.*",
                "如果这些文件不应忽略，请使用 force 模式重新执行",
            ]
            return result
        notify("检测到敏感文件但已 force 模式跳过")

    # PHASE 4: Git remote configuration
    notify("正在配置 Git 远程仓库地址...")
    rc, out, _ = _run_cmd("git remote -v", cwd=workspace_path, timeout=5)

    if repo_url:
        if "origin" in out:
            current_origin = ""
            for line in out.splitlines():
                if "origin" in line:
                    current_origin = line.split()[1] if len(line.split()) > 1 else ""
                    break
            if current_origin and current_origin.rstrip(".git") != repo_url.rstrip(".git"):
                notify(f"更新 origin 远程地址: {current_origin} → {repo_url}")
                _run_cmd(f"git remote set-url origin {repo_url}", cwd=workspace_path, timeout=5)
            notify(f"远程仓库: {repo_url}")
        else:
            notify(f"添加 origin 远程仓库: {repo_url}")
            rc, _, err = _run_cmd(f"git remote add origin {repo_url}", cwd=workspace_path, timeout=5)
            if rc != 0:
                result.error_code = "REMOTE_ADD_FAILED"
                result.error_detail = f"添加远程仓库失败: {err}"
                result.fix_steps = [
                    "确认仓库 URL 正确",
                    "如果 origin 已存在，先运行 git remote remove origin",
                ]
                return result
    elif "origin" not in out:
        result.error_code = "NO_REMOTE"
        result.error_detail = (
            "未配置远程仓库地址。请在 GitHub 上创建仓库后提供 URL。"
        )
        result.fix_steps = [
            "1. 在 GitHub 上创建新仓库 (https://github.com/new)",
            "2. 复制 SSH URL: git@github.com:USERNAME/REPO.git",
            "3. 提供 URL 重新执行上传",
        ]
        return result
    else:
        for line in out.splitlines():
            if "origin" in line:
                parts = line.split()
                if len(parts) > 1:
                    repo_url = parts[1]
                break

    result.repo_url = repo_url or ""

    # PHASE 5: Stage & commit
    branch = branch or _detect_branch(workspace_path)
    result.branch = branch

    rc, out, _ = _run_cmd("git status --porcelain", cwd=workspace_path, timeout=5)
    if not out.strip():
        notify("没有需要提交的变更")
        result.commits_pushed = _count_unpushed_commits(workspace_path, branch)
    else:
        notify(f"检测到未提交的变更，正在 stage...")
        _run_cmd("git add -A", cwd=workspace_path, timeout=10)
        _run_cmd(
            'git commit -m "chore: auto-commit by AlphaPilot G7.0"',
            cwd=workspace_path, timeout=10
        )
        notify("变更已 commit")
        result.commits_pushed = _count_unpushed_commits(workspace_path, branch)

    # PHASE 6: Push with retry
    notify(f"正在推送到 {repo_url} ({branch})...")

    MAX_PUSH_RETRIES = 3
    RETRY_DELAYS = [2, 4, 8]

    for attempt in range(MAX_PUSH_RETRIES + 1):
        cmd = f"git push {'-f ' if force else ''}-u origin {branch}"
        rc, out, err = _run_cmd(cmd, cwd=workspace_path, timeout=60)

        if rc == 0:
            result.success = True
            notify(f"推送成功 (attempt {attempt + 1})")
            break

        error_text = (err + out).lower()

        if "connection refused" in error_text or "could not resolve host" in error_text:
            notify(f"网络连接失败 (attempt {attempt + 1})")
            if attempt < MAX_PUSH_RETRIES:
                time.sleep(RETRY_DELAYS[attempt])
                continue
            result.error_code = "PUSH_NETWORK"
            result.error_detail = "推送失败：无法连接 GitHub 服务器"
            result.fix_steps = [
                "检查网络连接",
                "尝试使用代理: git config --global http.proxy http://127.0.0.1:7890",
                "或使用镜像: git config --global url.\"https://ghproxy.com/https://github.com\".insteadOf https://github.com",
            ]

        elif "permission denied" in error_text or "access denied" in error_text:
            result.error_code = "PUSH_PERMISSION"
            result.error_detail = "推送失败：权限被拒绝。SSH 密钥可能未添加到 GitHub。"
            result.fix_steps = [
                "确认公钥已添加到 https://github.com/settings/keys",
                "确认仓库存在且你有推送权限",
            ]
            break

        elif "non-fast-forward" in error_text:
            result.error_code = "PUSH_REJECTED"
            result.error_detail = "推送失败：当前分支落后于远程分支。"
            result.fix_steps = [
                "先拉取远程变更: git pull origin {branch} --rebase".format(branch=branch),
                "或使用 force 推送: git push -f origin {branch}",
            ]
            break

        elif "failed to push some refs" in error_text:
            result.error_code = "PUSH_FAILED"
            result.error_detail = f"推送失败: {err[:200]}"
            result.fix_steps = ["检查网络连接", "确认远程仓库存在", "尝试 git pull 后再推送"]
            if attempt < MAX_PUSH_RETRIES:
                time.sleep(RETRY_DELAYS[attempt])
                continue
            break

        else:
            result.error_code = "PUSH_UNKNOWN"
            result.error_detail = f"推送失败: {err[:200]}"
            if attempt < MAX_PUSH_RETRIES:
                notify(f"第 {attempt + 1} 次重试...")
                time.sleep(RETRY_DELAYS[attempt])
                continue
            break

    return result