"""Run the narrow set of project tools supported by workspace-maintenance tasks."""

import os
import re
import subprocess
import sys
from pathlib import Path

ENV_DIRECTORY_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])\.(?:vnev|venv)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
VENV_REQUEST_PATTERN = re.compile(r"虚拟环境|virtual[\s_-]*environment|\bvenv\b", re.IGNORECASE)
INSTALL_REQUEST_PATTERN = re.compile(
    r"安装.{0,12}(?:依赖|库|包)|install.{0,24}(?:dependenc|packag)|pip\s+install|"
    r"补装.{0,16}(?:依赖|库|包|fastapi|uvicorn|pytest|numpy|模块)|"
    r"执行安装|帮我安装|请安装|需要补装|需要安装|补装\b|补上依赖|装上依赖|"
    r"安装.{0,8}(?:fastapi|uvicorn|pytest|numpy)|"
    r"(?:缺少|没有|缺失|需要).{0,8}(?:fastapi|uvicorn|pytest).{0,8}(?:安装|补装|装上)",
    re.IGNORECASE,
)


def detect_environment_requests(prompt):
    """Return explicit environment actions and the requested environment directory."""
    text = prompt if isinstance(prompt, str) else ""
    requested_name = ENV_DIRECTORY_PATTERN.search(text)
    return {
        "create_venv": bool(VENV_REQUEST_PATTERN.search(text) or INSTALL_REQUEST_PATTERN.search(text)),
        "install_dependencies": bool(INSTALL_REQUEST_PATTERN.search(text)),
        "venv_name": requested_name.group(0) if requested_name else ".venv",
    }


def setup_python_environment(
    workspace_path,
    venv_name,
    create_venv,
    install_dependencies,
    progress,
    inferred_dependencies=None,
):
    """Create/reuse a project venv and install declared or source-inferred dependencies."""
    root = Path(workspace_path).resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"工作区路径不是目录: {workspace_path}")
    if venv_name not in {".venv", ".vnev"}:
        raise ValueError(f"不支持的虚拟环境目录: {venv_name}")

    operations = []
    environment_path = root / venv_name
    resolved_environment = environment_path.resolve(strict=False)
    try:
        resolved_environment.relative_to(root)
    except ValueError as error:
        raise ValueError("虚拟环境路径超出工作区范围。") from error
    if environment_path.is_symlink():
        raise ValueError(f"虚拟环境目录不能是符号链接: {venv_name}")

    if create_venv:
        environment_python = _venv_python(environment_path)
        if environment_path.exists():
            if not environment_python.is_file():
                raise RuntimeError(
                    f"{venv_name} 已存在，但未找到可用的 Python 解释器；为避免覆盖现有内容，已停止。"
                )
            operations.append({
                "name": "create_venv",
                "status": "reused",
                "path": str(environment_path),
                "output": "已复用现有虚拟环境。",
            })
            progress(f"复用现有虚拟环境 {venv_name}")
        else:
            progress(f"正在创建虚拟环境 {venv_name}")
            command = [sys.executable, "-m", "venv", str(environment_path)]
            result = _run(command, root, timeout=300)
            operations.append(_command_operation("create_venv", command, result))
            if result["exit_code"] != 0:
                return operations
            environment_python = _venv_python(environment_path)
            if not environment_python.is_file():
                operations[-1]["status"] = "failed"
                operations[-1]["stderr"] = (
                    f"虚拟环境命令成功，但没有找到解释器: {environment_python}"
                )
                return operations
    else:
        environment_python = _venv_python(environment_path)
        if not environment_python.is_file():
            operations.append({
                "name": "install_dependencies",
                "status": "skipped",
                "output": f"未请求创建虚拟环境，且 {venv_name} 不存在；未安装依赖。",
            })
            return operations

    if not install_dependencies:
        return operations

    manifests = _dependency_manifests(root)
    inferred_dependencies = sorted(
        {
            dependency.strip()
            for dependency in (inferred_dependencies or [])
            if isinstance(dependency, str) and dependency.strip()
        },
        key=str.casefold,
    )
    if not manifests and not inferred_dependencies:
        operations.append({
            "name": "install_dependencies",
            "status": "skipped",
            "output": "未找到依赖清单，源码中也未识别到可安全映射的第三方依赖；未猜测安装。",
        })
        return operations

    for manifest in manifests:
        resolved_manifest = manifest.resolve(strict=True)
        try:
            resolved_manifest.relative_to(root)
        except ValueError as error:
            raise ValueError(f"依赖清单超出工作区范围: {manifest.name}") from error
        progress(f"正在使用 {manifest.name} 安装项目依赖")
        if manifest.name.lower().startswith("requirements") and manifest.suffix.lower() == ".txt":
            command = [
                str(environment_python),
                "-m",
                "pip",
                "--disable-pip-version-check",
                "--no-input",
                "install",
                "-r",
                str(resolved_manifest),
            ]
        else:
            command = [
                str(environment_python),
                "-m",
                "pip",
                "--disable-pip-version-check",
                "--no-input",
                "install",
                "-e",
                str(root),
            ]

        result = _run(command, root, timeout=900)
        operation = _command_operation("install_dependencies", command, result)
        operation["manifest"] = manifest.relative_to(root).as_posix()
        operations.append(operation)
        if result["exit_code"] != 0:
            break
    else:
        if inferred_dependencies:
            progress("根据 Python 源码导入安装依赖：" + ", ".join(inferred_dependencies))
            command = [
                str(environment_python),
                "-m",
                "pip",
                "--disable-pip-version-check",
                "--no-input",
                "install",
                *inferred_dependencies,
            ]
            result = _run(command, root, timeout=900)
            operations.append(_command_operation("install_inferred_dependencies", command, result))

    return operations


def _dependency_manifests(root):
    requirements = root / "requirements.txt"
    if requirements.is_file():
        return [requirements]
    alternatives = [
        root / "pyproject.toml",
        root / "setup.py",
        root / "requirements-dev.txt",
    ]
    return [path for path in alternatives if path.is_file()][:1]


def _venv_python(environment_path):
    if os.name == "nt":
        return environment_path / "Scripts" / "python.exe"
    return environment_path / "bin" / "python"


def _run(command, cwd, timeout):
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            check=False,
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
        }
    except subprocess.TimeoutExpired as error:
        return {
            "exit_code": 124,
            "stdout": _as_text(error.stdout),
            "stderr": f"命令执行超时 ({timeout}s)",
        }
    except OSError as error:
        return {"exit_code": 1, "stdout": "", "stderr": str(error)}


def _as_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def _command_operation(name, command, result):
    successful = result["exit_code"] == 0
    output = "\n".join((result.get("stdout", ""), result.get("stderr", "")))
    return {
        "name": name,
        "status": "completed" if successful else "failed",
        "command": command,
        "exit_code": result["exit_code"],
        "stdout": result["stdout"][-8_000:],
        "stderr": result["stderr"][-8_000:],
        "installed_packages": _installed_packages(output) if successful else [],
    }


def _installed_packages(output):
    match = re.search(r"(?mi)^Successfully installed\s+(.+?)\s*$", output or "")
    if not match:
        return []

    packages = {}
    for package_spec in match.group(1).split():
        name, separator, version = package_spec.rpartition("-")
        if separator and name and version and version[0].isdigit():
            normalized_name = re.sub(r"[-_.]+", "-", name).casefold()
            packages[normalized_name] = name
    return sorted(packages.values(), key=str.casefold)