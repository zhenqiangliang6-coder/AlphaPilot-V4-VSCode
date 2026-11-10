# -*- coding: utf-8 -*-
"""runtime_environment_recovery.py
P0「运行期环境自愈」— Python 测试命令自愈（第一版严格限定）

实现 7 步执行链：
  Probe（探测）→ Diagnose（分类）→ Authorize（授权）→ Recover（隔离修复）
  → Retry（有限重试）→ Degrade（安全降级）→ Evidence（证据记录）

安全契约（红线，不可违反）：
  1. 自愈层绝不能把「无法验证」误报为「验证通过」。
  2. 任何安装动作都必须经过授权；授权违规次数恒为 0。
  3. unittest 或手动执行不能替代 pytest 验收结果。

输入契约（context["meta"]）：
  - workspace_path (str)：工作区根目录
  - install_authorized (bool)：R6 授权门的 install 扩展
  - authorized_test_command (str)：原始测试命令（默认 python -m pytest）

输出契约（RecoveryResult dict）：
  status / failure_class / original_command / recovery_command /
  retry_count / install_actions / authorization / verification_status / evidence

与降级决策表（权威口径）对齐，详见 runtime_environment_recovery.md。
"""

import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

_INSTALL_TIMEOUT = 60
_TEST_TIMEOUT = 120
_PROBE_TIMEOUT = 30


class FailureClass:
    RUNNER_MISSING = "RUNNER_MISSING"
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
    DEPENDENCY_CONFLICT = "DEPENDENCY_CONFLICT"
    TEST_ASSERTION_FAILURE = "TEST_ASSERTION_FAILURE"
    UNSUPPORTED_TEST_RUNNER = "UNSUPPORTED_TEST_RUNNER"
    NO_EXECUTABLE_TESTS = "NO_EXECUTABLE_TESTS"
    INSTALL_TIMEOUT = "INSTALL_TIMEOUT"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"


class Status:
    RECOVERED = "recovered"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


class Verification:
    PASSED = "passed"
    FAILED = "failed"
    NOT_VERIFIED = "not_verified"


_SKIP_DIRS = {".venv", ".vnev", "__pycache__", ".pytest_cache", "node_modules"}


def recover_test_environment(workspace, context=None):
    """运行期环境自愈入口：探测 → 分类 → 授权 → 修复 → 重试 → 降级 → 证据。

    参数:
        workspace: 工作区根目录（str 或 Path）
        context: 请求上下文，读取 context["meta"] 中的输入契约

    返回:
        RecoveryResult dict，契约键见模块 docstring。
    """
    meta = (context or {}).get("meta", {}) or {}
    workspace = meta.get("workspace_path") or workspace
    install_authorized = bool(meta.get("install_authorized", True))
    test_command = meta.get("authorized_test_command") or "python -m pytest"

    result = {
        "status": Status.DEGRADED,
        "failure_class": None,
        "original_command": test_command,
        "recovery_command": None,
        "retry_count": 0,
        "install_actions": [],
        "authorization": {
            "required": True,
            "granted": install_authorized,
            "checked": False,
        },
        "verification_status": Verification.NOT_VERIFIED,
        "evidence": [],
        "final_test_result": None,
    }

    def evidence(stage, detail):
        result["evidence"].append({"stage": stage, "detail": detail})

    # ---- Probe：扫描可执行测试 + 探测 pytest 可用性 ----
    has_pytest_tests, has_unittest_tests, has_any_tests = _scan_tests(workspace)

    # S6：没有任何可执行测试 → 标记验证未完成，绝不判定通过
    if not has_any_tests:
        result["failure_class"] = FailureClass.NO_EXECUTABLE_TESTS
        result["status"] = Status.DEGRADED
        result["verification_status"] = Verification.NOT_VERIFIED
        evidence("diagnose", "no executable test files found in workspace")
        return result

    pytest_available = _probe_pytest()
    evidence("probe", "pytest available={}".format(pytest_available))

    # ---- Diagnose：pytest 不可用 ----
    if not pytest_available:
        # S5：仅有 unittest 测试（无 pytest 测试）→ 仅辅助诊断，不替代验收
        if not has_pytest_tests:
            result["failure_class"] = FailureClass.UNSUPPORTED_TEST_RUNNER
            result["status"] = Status.DEGRADED
            result["verification_status"] = Verification.NOT_VERIFIED
            if has_unittest_tests:
                diagnostic = _run_unittest_diagnostic(workspace)
                evidence("diagnose", "unittest diagnostic outcome={}".format(diagnostic))
            else:
                evidence("diagnose", "no pytest-style tests and pytest unavailable")
            return result

        # S1：pytest 缺失但存在 pytest 风格测试 → RUNNER_MISSING
        result["failure_class"] = FailureClass.RUNNER_MISSING
        evidence("diagnose", "pytest runner missing")

        # ---- Authorize：任何安装动作必须经过授权门 ----
        if not install_authorized:
            result["failure_class"] = FailureClass.AUTHORIZATION_DENIED
            result["status"] = Status.BLOCKED
            result["authorization"]["checked"] = True
            result["authorization"]["granted"] = False
            evidence("authorize", "installation denied by authorization gate")
            return result

        result["authorization"]["checked"] = True
        result["authorization"]["granted"] = True
        evidence("authorize", "installation authorized")

        # ---- Recover：隔离安装 pytest ----
        install = _install_packages(workspace, ["pytest"])
        result["install_actions"] = install["actions"]
        result["recovery_command"] = install["command"]
        if install["timed_out"]:
            result["failure_class"] = FailureClass.INSTALL_TIMEOUT
            result["status"] = Status.DEGRADED
            result["verification_status"] = Verification.NOT_VERIFIED
            evidence("recover", "pytest install timed out")
            return result
        if not install["success"]:
            result["status"] = Status.DEGRADED
            result["verification_status"] = Verification.NOT_VERIFIED
            evidence("recover", "pytest install failed; stop automatic install")
            return result
        evidence("recover", "pytest installed")

        # ---- Retry：有限重试 ----
        result["retry_count"] += 1
        outcome = _run_test_command(workspace, test_command)
        result["final_test_result"] = outcome
        if outcome["passed"]:
            result["status"] = Status.RECOVERED
            result["verification_status"] = Verification.PASSED
            evidence("retry", "tests passed after recovery")
        else:
            # 安装成功后仍失败：重新分类，可能是真实断言失败
            new_class = _diagnose_test_failure(outcome.get("stderr") or "")
            result["failure_class"] = new_class
            result["status"] = Status.DEGRADED
            result["verification_status"] = Verification.FAILED
            evidence("retry", "tests still failing after recovery; reclassified as {}".format(new_class))
        return result

    # ---- pytest 可用：直接运行原测试命令 ----
    outcome = _run_test_command(workspace, test_command)
    result["final_test_result"] = outcome
    if outcome["passed"]:
        result["status"] = Status.RECOVERED
        result["verification_status"] = Verification.PASSED
        result["failure_class"] = None
        evidence("retry", "tests passed")
        return result

    # ---- Diagnose：测试失败分类 ----
    stderr = outcome.get("stderr") or ""
    failure_class = _diagnose_test_failure(stderr)
    evidence("diagnose", "test failure classified as {}".format(failure_class))

    # S4：测试代码失败（断言错误）→ 禁止自愈，进 fix 流程
    if failure_class == FailureClass.TEST_ASSERTION_FAILURE:
        result["failure_class"] = FailureClass.TEST_ASSERTION_FAILURE
        result["status"] = Status.DEGRADED
        result["verification_status"] = Verification.FAILED
        evidence("degrade", "test code failure; hand off to existing fix loop")
        return result

    # S2 / S3：依赖缺失 / 版本冲突 → 遵循依赖声明修复
    result["failure_class"] = failure_class
    package = _extract_package(stderr)
    dependency = _resolve_dependency(workspace, package) if package else None
    if not dependency:
        result["status"] = Status.DEGRADED
        result["verification_status"] = Verification.NOT_VERIFIED
        evidence("recover", "could not resolve dependency declaration")
        return result

    # ---- Authorize：安装动作必须经过授权门 ----
    if not install_authorized:
        result["failure_class"] = FailureClass.AUTHORIZATION_DENIED
        result["status"] = Status.BLOCKED
        result["authorization"]["checked"] = True
        result["authorization"]["granted"] = False
        evidence("authorize", "installation denied by authorization gate")
        return result

    result["authorization"]["checked"] = True
    result["authorization"]["granted"] = True
    evidence("authorize", "installation authorized")

    # ---- Recover：按依赖声明安装 ----
    install = _install_packages(workspace, [dependency])
    result["install_actions"] = install["actions"]
    result["recovery_command"] = install["command"]
    if install["timed_out"]:
        result["failure_class"] = FailureClass.INSTALL_TIMEOUT
        result["status"] = Status.DEGRADED
        result["verification_status"] = Verification.NOT_VERIFIED
        evidence("recover", "dependency install timed out")
        return result
    if not install["success"]:
        result["status"] = Status.DEGRADED
        result["verification_status"] = Verification.NOT_VERIFIED
        evidence("recover", "dependency install failed; stop automatic install")
        return result
    evidence("recover", "dependency installed: {}".format(dependency))

    # ---- Retry：有限重试 ----
    result["retry_count"] += 1
    outcome = _run_test_command(workspace, test_command)
    result["final_test_result"] = outcome
    if outcome["passed"]:
        result["status"] = Status.RECOVERED
        result["verification_status"] = Verification.PASSED
        evidence("retry", "tests passed after recovery")
    else:
        # 安装成功后仍失败：重新分类，可能是真实断言失败或仍缺依赖
        new_class = _diagnose_test_failure(outcome.get("stderr") or "")
        result["failure_class"] = new_class
        result["status"] = Status.DEGRADED
        result["verification_status"] = Verification.FAILED
        evidence("retry", "tests still failing after recovery; reclassified as {}".format(new_class))
    return result


# ================================================================
#  内部工具函数
# ================================================================

def _probe_pytest():
    """探测 pytest 是否可用：先查 PATH，再尝试以模块方式导入。"""
    if shutil.which("pytest"):
        return True
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--version"],
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _scan_tests(workspace):
    """扫描工作区中的测试文件，区分 pytest 风格与 unittest 风格。

    返回:
        (has_pytest_tests, has_unittest_tests, has_any_tests)
    """
    root = Path(workspace)
    has_pytest_tests = False
    has_unittest_tests = False
    has_any_tests = False

    for path in _iter_test_files(root):
        has_any_tests = True
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "unittest" in content:
            has_unittest_tests = True
        else:
            has_pytest_tests = True
    return has_pytest_tests, has_unittest_tests, has_any_tests


def _iter_test_files(root):
    if not root.is_dir():
        return
    for path in root.rglob("*.py"):
        if not path.is_file():
            continue
        name = path.name
        if not (name.startswith("test_") or name.endswith("_test.py")):
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        yield path


def _diagnose_test_failure(stderr):
    """将测试失败输出分类为故障类型（按优先级，冲突优先于缺失）。"""
    if not stderr:
        return FailureClass.TEST_ASSERTION_FAILURE
    low = stderr.lower()
    if "version conflict" in low or ("conflict" in low and "required" in low):
        return FailureClass.DEPENDENCY_CONFLICT
    if "modulenotfounderror" in low or "no module named" in low or "importerror" in low:
        return FailureClass.DEPENDENCY_MISSING
    return FailureClass.TEST_ASSERTION_FAILURE


def _extract_package(stderr):
    """从失败输出中提取缺失/冲突的包名（best-effort）。"""
    match = re.search(r"[Nn]o module named ['\"]?([A-Za-z0-9_]+)", stderr)
    if match:
        return match.group(1)
    match = re.search(r"(?:ImportError|ModuleNotFoundError):\s*([A-Za-z0-9_]+)", stderr)
    if match:
        return match.group(1)
    return None


def _resolve_dependency(workspace, package):
    """按项目依赖声明解析要安装的包（遵循声明，禁止无条件升级/降级）。"""
    if not package:
        return None
    requirements = Path(workspace) / "requirements.txt"
    if requirements.is_file():
        try:
            for line in requirements.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                name = re.split(r"[<>=!~\[\];]", line)[0].strip()
                if name and name.lower() == package.lower():
                    return line
        except OSError:
            pass
    return package


def _install_packages(workspace, packages):
    """执行 pip 安装，返回 {success, timed_out, command, actions}。

    安装动作统一标记 authorized=True（调用方已先经过授权门）。
    """
    command = [sys.executable, "-m", "pip", "install", *packages]
    command_str = " ".join(command)
    actions = []
    try:
        result = subprocess.run(
            command,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=_INSTALL_TIMEOUT,
        )
        success = result.returncode == 0
        actions.append({
            "command": command_str,
            "authorized": True,
            "outcome": "success" if success else "failure",
        })
        return {
            "success": success,
            "timed_out": False,
            "command": command_str,
            "actions": actions,
        }
    except subprocess.TimeoutExpired:
        actions.append({
            "command": command_str,
            "authorized": True,
            "outcome": "timeout",
        })
        return {
            "success": False,
            "timed_out": True,
            "command": command_str,
            "actions": actions,
        }


def _run_test_command(workspace, command):
    """执行原始测试命令，返回 {passed, stdout, stderr}。"""
    try:
        args = shlex.split(command)
    except ValueError:
        args = command.split()
    try:
        result = subprocess.run(
            args,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=_TEST_TIMEOUT,
        )
        return {
            "passed": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "exit_code": None, "stdout": "", "stderr": "test timed out"}
    except FileNotFoundError as exc:
        return {"passed": False, "exit_code": None, "stdout": "", "stderr": "command not found: {}".format(exc)}


def _run_unittest_diagnostic(workspace):
    """仅作辅助诊断：运行 unittest，结果不替代 pytest 验收。"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=_TEST_TIMEOUT,
        )
        return "passed" if result.returncode == 0 else "failed"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "not_available"