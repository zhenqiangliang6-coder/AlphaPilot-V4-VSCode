# -*- coding: utf-8 -*-
"""
tests/test_eval_baseline.py
P0「运行期环境自愈」红线基线（Eval Harness）

用途
====
本文件在 P0 实现之前锁定「安全契约」。它验证的是**系统行为**（可观测的
RecoveryResult 与授权/验证不变量），而不是未来实现的内部细节。

设计原则（先锁定安全契约，再让 P0 实现去满足它）：
1. 自愈层绝不能把「无法验证」误报为「验证通过」。
2. 任何安装动作都必须经过授权；授权违规次数必须恒为 0。
3. unittest 或手动执行不能替代 pytest 验收结果。

当前状态
========
runtime_environment_recovery 尚未实现（Phase 2），本文件的测试会 SKIP。
实现完成后，这些测试从 SKIP 变为 RUN，必须全部通过。

场景 → 期望（降级决策表，权威口径）
====================================
S1  RUNNER_MISSING         pytest 缺失             授权后隔离安装 → 恢复(verified=passed)
S2  DEPENDENCY_MISSING     测试依赖缺失            按依赖声明修复 → 恢复
S3  DEPENDENCY_CONFLICT    版本冲突                遵循声明与授权，禁止无条件升级/降级
S4  TEST_ASSERTION_FAILURE 测试代码失败            禁止自愈，进 fix 流程(verified=failed)
S5  UNSUPPORTED_TEST_RUNNER pytest 无法运行但有 unittest  仅辅助诊断，不替代结果(verified=not_verified)
S6  NO_EXECUTABLE_TESTS    无可执行测试            标记验证未完成，不得判定通过
S7  INSTALL_TIMEOUT        安装超时                终止安装、记录证据、不无限重试
S8  AUTHORIZATION_DENIED   授权拒绝                不安装、不绕过授权、验证未完成

四个度量（Eval Harness 红线）：
  1. 恢复成功率（S1-S3 应 recovered）
  2. 恢复成本（retry_count / install_calls 有界，不无限重试）
  3. 误报率（S5/S6 不得 verified=passed，恒为 0）
  4. 授权违规次数（任何 install_actions 的 authorized 恒为 True，S8 恒为 0 次安装）
"""

import subprocess as sp
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # Copilot_Alphapilot/
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# 安全契约常量（权威口径）
# ---------------------------------------------------------------------------
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


ALL_FAILURE_CLASSES = {
    FailureClass.RUNNER_MISSING,
    FailureClass.DEPENDENCY_MISSING,
    FailureClass.DEPENDENCY_CONFLICT,
    FailureClass.TEST_ASSERTION_FAILURE,
    FailureClass.UNSUPPORTED_TEST_RUNNER,
    FailureClass.NO_EXECUTABLE_TESTS,
    FailureClass.INSTALL_TIMEOUT,
    FailureClass.AUTHORIZATION_DENIED,
}

ALL_STATUSES = {Status.RECOVERED, Status.DEGRADED, Status.BLOCKED}
ALL_VERIFICATION = {Verification.PASSED, Verification.FAILED, Verification.NOT_VERIFIED}

# RecoveryResult 的必需键（契约 Schema）
REQUIRED_RESULT_KEYS = {
    "status",
    "failure_class",
    "original_command",
    "recovery_command",
    "retry_count",
    "install_actions",
    "authorization",
    "verification_status",
    "evidence",
}


# ---------------------------------------------------------------------------
# 导入 P0 模块（Phase 2 之前 SKIP）
# ---------------------------------------------------------------------------
recovery = pytest.importorskip(
    "python_worker.runtime_environment_recovery",
    reason="P0 未实现：runtime_environment_recovery 模块尚未创建（Phase 2）",
)
recover_test_environment = recovery.recover_test_environment


# ---------------------------------------------------------------------------
# 契约 Schema 校验
# ---------------------------------------------------------------------------
def _assert_schema(result):
    assert isinstance(result, dict), f"RecoveryResult 必须是 dict，实际 {type(result)}"
    missing = REQUIRED_RESULT_KEYS - set(result.keys())
    assert not missing, f"RecoveryResult 缺少必需键: {sorted(missing)}"
    assert result["status"] in ALL_STATUSES, f"非法 status: {result['status']}"
    assert result["verification_status"] in ALL_VERIFICATION, (
        f"非法 verification_status: {result['verification_status']}"
    )
    assert result["failure_class"] is None or result["failure_class"] in ALL_FAILURE_CLASSES, (
        f"非法 failure_class: {result['failure_class']}"
    )
    assert isinstance(result["retry_count"], int) and result["retry_count"] >= 0
    assert isinstance(result["install_actions"], list)
    assert isinstance(result["authorization"], dict)
    assert isinstance(result["evidence"], list)


def _assert_no_auth_violation(result):
    """硬性安全指标：任何安装动作都必须是已授权的。"""
    for action in result["install_actions"]:
        assert action.get("authorized") is True, f"存在未授权安装动作: {action}"


# ---------------------------------------------------------------------------
# OS 边界假环境
# ---------------------------------------------------------------------------
class _FakeSubprocess:
    """模拟 subprocess.run 的行为，按命令内容分派。

    这不是在写实现细节，而是控制最自然的 OS 边界（命令执行），
    让测试得以驱动 Probe / Recover / Retry 的每一步结果。
    """

    def __init__(
        self,
        *,
        pytest_present,
        install_outcome="success",  # success | failure | timeout
        test_outcome="pass",        # pass | fail
        test_stderr="",
        unittest_outcome="pass",
    ):
        self.pytest_present = pytest_present
        self.install_outcome = install_outcome
        self.test_outcome = test_outcome
        self.test_stderr = test_stderr
        self.unittest_outcome = unittest_outcome
        self.healed = False
        self.install_calls = 0
        self.install_commands = []
        self.test_calls = 0
        self.unittest_calls = 0

    def run(self, args, **kwargs):
        cmd = " ".join(str(a) for a in (args if isinstance(args, (list, tuple)) else [args]))

        # Probe：探测 pytest
        if "pytest" in cmd and ("--version" in cmd or "-V" in cmd):
            if not self.pytest_present:
                raise FileNotFoundError("pytest")
            return sp.CompletedProcess(args, 0, "pytest 8.0.0", "")

        # Recover：安装
        if "pip" in cmd and "install" in cmd:
            self.install_calls += 1
            self.install_commands.append(cmd)
            if self.install_outcome == "timeout":
                raise sp.TimeoutExpired(cmd, 60)
            if self.install_outcome == "failure":
                return sp.CompletedProcess(args, 1, "", "ERROR: installation failed")
            self.healed = True
            self.pytest_present = True
            return sp.CompletedProcess(args, 0, "Successfully installed", "")

        # unittest 辅助诊断
        if "unittest" in cmd:
            self.unittest_calls += 1
            rc = 0 if self.unittest_outcome == "pass" else 1
            return sp.CompletedProcess(args, rc, "Ran 2 tests\nOK" if rc == 0 else "FAILED", "")

        # Retry / 测试执行
        self.test_calls += 1
        if self.healed or self.test_outcome == "pass":
            return sp.CompletedProcess(args, 0, "2 passed", "")
        return sp.CompletedProcess(args, 1, "", self.test_stderr or "AssertionError")


def _which_factory(pytest_present):
    def which(program):
        if program in ("pytest",):
            return "/fake/bin/pytest" if pytest_present else None
        return f"/fake/bin/{program}"

    return which


# ---------------------------------------------------------------------------
# 输入契约构建器
# ---------------------------------------------------------------------------
def _context(workspace, *, install_authorized=True, test_command="python -m pytest"):
    """P0 输入契约：
    - meta.install_authorized (bool)：安装授权标志（R6 授权门的 install 扩展）
    - meta.authorized_test_command (str)：原始测试命令
    """
    return {
        "meta": {
            "workspace_path": str(workspace),
            "install_authorized": install_authorized,
            "authorized_test_command": test_command,
        }
    }


def _make_workspace(tmp_path, *, pytest_tests=True, unittest_tests=False, requirements=None):
    tests = tmp_path / "tests"
    tests.mkdir(exist_ok=True)
    if pytest_tests:
        (tests / "test_x.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    if unittest_tests:
        (tests / "test_u.py").write_text(
            "import unittest\n\n"
            "class TestX(unittest.TestCase):\n"
            "    def test_ok(self):\n"
            "        self.assertTrue(True)\n",
            encoding="utf-8",
        )
    if requirements:
        (tmp_path / "requirements.txt").write_text(requirements, encoding="utf-8")
    return tmp_path


# ========================================================================
# S1  RUNNER_MISSING：pytest 缺失 → 授权后隔离安装 → 恢复
# ========================================================================
def test_S1_runner_missing_recovers_after_authorized_install(tmp_path):
    ws = _make_workspace(tmp_path)
    fake = _FakeSubprocess(pytest_present=False, install_outcome="success", test_outcome="pass")

    with patch("subprocess.run", side_effect=fake.run), patch("shutil.which", side_effect=_which_factory(False)):
        result = recover_test_environment(str(ws), _context(ws))

    _assert_schema(result)
    _assert_no_auth_violation(result)
    assert result["failure_class"] == FailureClass.RUNNER_MISSING
    assert result["status"] == Status.RECOVERED
    assert result["verification_status"] == Verification.PASSED
    assert result["retry_count"] >= 1
    assert fake.install_calls == 1
    assert result["original_command"] is not None


# ========================================================================
# S2  DEPENDENCY_MISSING：测试依赖缺失 → 按依赖声明修复 → 恢复
# ========================================================================
def test_S2_dependency_missing_recovers_per_declaration(tmp_path):
    ws = _make_workspace(tmp_path, requirements="requests\n")
    fake = _FakeSubprocess(
        pytest_present=True,
        install_outcome="success",
        test_outcome="fail",
        test_stderr="ModuleNotFoundError: No module named 'requests'",
    )

    with patch("subprocess.run", side_effect=fake.run), patch("shutil.which", side_effect=_which_factory(True)):
        result = recover_test_environment(str(ws), _context(ws))

    _assert_schema(result)
    _assert_no_auth_violation(result)
    assert result["failure_class"] == FailureClass.DEPENDENCY_MISSING
    assert result["status"] == Status.RECOVERED
    assert result["verification_status"] == Verification.PASSED
    assert fake.install_calls == 1
    assert any("requests" in c for c in fake.install_commands), (
        f"安装动作未遵循依赖声明: {fake.install_commands}"
    )


# ========================================================================
# S3  DEPENDENCY_CONFLICT：版本冲突 → 遵循声明与授权，禁止无条件升级/降级
# ========================================================================
def test_S3_dependency_conflict_follows_declaration_not_unconditional_upgrade(tmp_path):
    ws = _make_workspace(tmp_path, requirements="requests==2.28.0\n")
    fake = _FakeSubprocess(
        pytest_present=True,
        install_outcome="success",
        test_outcome="fail",
        test_stderr="ImportError: requests version conflict (installed 2.31.0, required 2.28.0)",
    )

    with patch("subprocess.run", side_effect=fake.run), patch("shutil.which", side_effect=_which_factory(True)):
        result = recover_test_environment(str(ws), _context(ws))

    _assert_schema(result)
    _assert_no_auth_violation(result)
    assert result["failure_class"] == FailureClass.DEPENDENCY_CONFLICT
    assert result["status"] == Status.RECOVERED
    assert result["verification_status"] == Verification.PASSED
    # 必须遵循项目依赖声明（安装 pinned 版本），而不是无条件升级/降级
    assert any("2.28.0" in c for c in fake.install_commands), (
        f"冲突修复未遵循依赖声明（应安装 2.28.0）: {fake.install_commands}"
    )


# ========================================================================
# S4  TEST_ASSERTION_FAILURE：测试代码失败 → 禁止自愈，进 fix 流程
# ========================================================================
def test_S4_test_assertion_failure_is_forbidden_to_recover(tmp_path):
    ws = _make_workspace(tmp_path)
    fake = _FakeSubprocess(
        pytest_present=True,
        install_outcome="success",
        test_outcome="fail",
        test_stderr="AssertionError: assert 1 == 2",
    )

    with patch("subprocess.run", side_effect=fake.run), patch("shutil.which", side_effect=_which_factory(True)):
        result = recover_test_environment(str(ws), _context(ws))

    _assert_schema(result)
    _assert_no_auth_violation(result)
    assert result["failure_class"] == FailureClass.TEST_ASSERTION_FAILURE
    assert result["status"] != Status.RECOVERED
    assert result["verification_status"] == Verification.FAILED
    assert fake.install_calls == 0, "测试代码失败时不得触发任何安装动作"


# ========================================================================
# S5  UNSUPPORTED_TEST_RUNNER：pytest 无法运行但有 unittest → 仅辅助诊断
# ========================================================================
def test_S5_unittest_is_diagnostic_only_never_substitutes_pytest(tmp_path):
    ws = _make_workspace(tmp_path, pytest_tests=False, unittest_tests=True)
    fake = _FakeSubprocess(pytest_present=False, unittest_outcome="pass")

    with patch("subprocess.run", side_effect=fake.run), patch("shutil.which", side_effect=_which_factory(False)):
        result = recover_test_environment(str(ws), _context(ws))

    _assert_schema(result)
    _assert_no_auth_violation(result)
    assert result["failure_class"] == FailureClass.UNSUPPORTED_TEST_RUNNER
    assert result["status"] != Status.RECOVERED
    # 硬性不变式：即使 unittest 全通过，也不得把 pytest 未运行改写为验证通过
    assert result["verification_status"] == Verification.NOT_VERIFIED, (
        "unittest 通过不得替代 pytest 验收结果"
    )


# ========================================================================
# S6  NO_EXECUTABLE_TESTS：无可执行测试 → 标记验证未完成，不得判定通过
# ========================================================================
def test_S6_no_executable_tests_marks_not_verified(tmp_path):
    ws = tmp_path  # 无 tests 目录、无任何测试文件

    with patch("subprocess.run", side_effect=_FakeSubprocess(pytest_present=True).run), \
         patch("shutil.which", side_effect=_which_factory(True)):
        result = recover_test_environment(str(ws), _context(ws))

    _assert_schema(result)
    _assert_no_auth_violation(result)
    assert result["failure_class"] == FailureClass.NO_EXECUTABLE_TESTS
    assert result["status"] != Status.RECOVERED
    assert result["verification_status"] == Verification.NOT_VERIFIED, "无可执行测试不得判定通过"


# ========================================================================
# S7  INSTALL_TIMEOUT：安装超时 → 终止安装、记录证据、不无限重试
# ========================================================================
def test_S7_install_timeout_stops_and_does_not_retry_forever(tmp_path):
    ws = _make_workspace(tmp_path)
    fake = _FakeSubprocess(pytest_present=False, install_outcome="timeout")

    with patch("subprocess.run", side_effect=fake.run), patch("shutil.which", side_effect=_which_factory(False)):
        result = recover_test_environment(str(ws), _context(ws))

    _assert_schema(result)
    _assert_no_auth_violation(result)
    assert result["failure_class"] == FailureClass.INSTALL_TIMEOUT
    assert result["status"] != Status.RECOVERED
    assert result["verification_status"] == Verification.NOT_VERIFIED
    assert fake.install_calls <= 1, f"安装超时不得无限重试，实际安装次数: {fake.install_calls}"
    assert len(result["evidence"]) >= 1, "安装超时必须记录证据"


# ========================================================================
# S8  AUTHORIZATION_DENIED：授权拒绝 → 不安装、不绕过授权、验证未完成
# ========================================================================
def test_S8_authorization_denied_never_installs(tmp_path):
    ws = _make_workspace(tmp_path)
    fake = _FakeSubprocess(pytest_present=False, install_outcome="success")

    with patch("subprocess.run", side_effect=fake.run), patch("shutil.which", side_effect=_which_factory(False)):
        result = recover_test_environment(str(ws), _context(ws, install_authorized=False))

    _assert_schema(result)
    _assert_no_auth_violation(result)
    assert result["failure_class"] == FailureClass.AUTHORIZATION_DENIED
    assert result["status"] == Status.BLOCKED
    assert result["verification_status"] == Verification.NOT_VERIFIED
    assert fake.install_calls == 0, "授权拒绝时不得发生任何安装动作"
    assert result["install_actions"] == [], "授权拒绝时 install_actions 必须为空"


# ========================================================================
# 硬性安全指标：授权违规次数恒为 0（跨全场景的防御性校验）
# ========================================================================
def test_authorization_violations_are_zero_when_denied_has_no_install(tmp_path):
    ws = _make_workspace(tmp_path)
    fake = _FakeSubprocess(pytest_present=False, install_outcome="success")

    with patch("subprocess.run", side_effect=fake.run), patch("shutil.which", side_effect=_which_factory(False)):
        result = recover_test_environment(str(ws), _context(ws, install_authorized=False))

    # 授权违规 = 未授权却发生了安装；此处断言为 0
    unauthorized = [
        a for a in result["install_actions"] if a.get("authorized") is not True
    ]
    assert unauthorized == []
    assert fake.install_calls == 0