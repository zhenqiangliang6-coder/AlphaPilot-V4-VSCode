# -*- coding: utf-8 -*-
# tests/test_real_pytest_and_retry.py
# v3.3 验证 test→fix→retest 闭环
# ================================================================
# 测试结构:
#   1. _run_pytest 函数级测试（不依赖 worker）
#   2. Worker retry loop 集成测试（mock execute_step）
#   3. 成功路径：初始失败→修复→重测通过
#   4. 失败路径：持续失败→3次上限→退出
# ================================================================

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# -------------------------------------------------------------------
# 路径准备 — 从项目根启动时 python_worker 是顶层包
# -------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # Copilot_Alphapilot/
sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker.agents.qwen.step_executor.test_step import _run_pytest
from python_worker.agents.qwen import step_runner
from python_worker.task_state_contract import (
    STEP_STATE_AWAITING_AUTHORIZATION,
    STEP_STATE_COMPLETED,
    STEP_STATE_FAILED,
    STEP_STATE_SKIPPED,
    STEP_STATE_PENDING,
)


class TestRunPytest:
    """L1: 验证 _run_pytest 真实子进程执行。"""

    @pytest.fixture
    def sandbox(self):
        d = tempfile.mkdtemp(prefix="ap_test_sandbox_")
        yield Path(d)
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    def test_passing_test(self, sandbox):
        code = "def add(a, b):\n    return a + b\n"
        test_code = (
            "import pytest\n"
            "from test_ap_generated import add\n"  # won't work... actually we need inline import
            "# Let's just test inline:\n"
            "def test_add():\n"
            "    assert add(1, 2) == 3\n"
        )
        # Actually pytest needs the source code to be importable. Let's combine.
        combined = "def add(a, b):\n    return a + b\n\ndef test_add():\n    assert add(1, 2) == 3\n"
        result = _run_pytest(str(sandbox), "", combined)
        assert result["passed"] is True
        assert result["exit_code"] == 0
        assert result["timed_out"] is False

    def test_failing_test(self, sandbox):
        combined = (
            "def add(a, b):\n    return a + b\n\n"
            "def test_add():\n    assert add(1, 2) == 5\n"
        )
        result = _run_pytest(str(sandbox), "", combined)
        assert result["passed"] is False
        assert result["exit_code"] == 1
        assert "5" in result["stdout"] or "assert" in result["stdout"].lower()

    def test_syntax_error(self, sandbox):
        combined = "def add(a b):\n    return a + b\n\ndef test_add():\n    assert add(1,2) == 3\n"
        result = _run_pytest(str(sandbox), "", combined)
        assert result["passed"] is False
        assert result["exit_code"] != 0

    def test_pytest_not_installed(self, sandbox):
        with patch("subprocess.run", side_effect=FileNotFoundError("pytest")):
            result = _run_pytest(str(sandbox), "x=1", "def test_x():\n    assert x==1\n")
        assert result["passed"] is False
        assert "not installed" in result["stderr"]

    def test_timeout(self, sandbox):
        import subprocess as sp_mod
        with patch.object(sp_mod, "TimeoutExpired", new=sp_mod.TimeoutExpired):
            mock = sp_mod.TimeoutExpired("pytest", 120)
            mock.stdout = "partial output"
            mock.stderr = ""
            with patch("subprocess.run", side_effect=mock):
                result = _run_pytest(str(sandbox), "x=1", "def test_x():\n    pass\n")
        assert result["passed"] is False
        assert result["timed_out"] is True
        assert result["stdout"] == "partial output"


class TestWorkerRetryLoop:
    """L3: 验证步骤执行器中的测试授权和 test→fix→retest 状态机。"""

    @staticmethod
    def _step(step_type):
        return {"type": step_type, "status": STEP_STATE_PENDING, "output": {}}

    @staticmethod
    def _run(steps, fake_exec, *, requires_authorization=False, context=None):
        context = context or {"meta": {}}
        with (
            patch.object(step_runner, "check_stop_flag", return_value=False),
            patch.object(step_runner, "stream_chunk"),
            patch.object(
                step_runner,
                "requires_authorization_before_step",
                return_value=requires_authorization,
            ),
            patch.object(step_runner, "execute_step", side_effect=fake_exec),
        ):
            step_runner.run_execution_loop(
                steps, {}, "", [], context, "write_code", "engineer"
            )
        return context

    def test_retry_success_path(self):
        calls = []

        def fake_exec(task_id, step, events, context):
            calls.append(step["type"])
            if step["type"] == "test":
                test_calls = calls.count("test")
                if test_calls == 1:
                    step["output"] = {
                        "text": "FAIL",
                        "exec_success": False,
                        "test_result": {"exit_code": 1, "timed_out": False},
                    }
                else:
                    step["output"] = {"text": "PASS", "exec_success": True}
            else:
                step["output"] = {"text": "fixed", "file_ops": [{"path": "src/a.py"}]}

        steps = [self._step("test"), self._step("fix")]
        self._run(steps, fake_exec)

        assert calls == ["test", "fix", "test"]
        assert steps[0]["status"] == STEP_STATE_COMPLETED
        assert steps[1]["status"] == STEP_STATE_SKIPPED

    def test_retry_failure_path_stops_after_three_retries(self):
        calls = []

        def fake_exec(task_id, step, events, context):
            calls.append(step["type"])
            if step["type"] == "test":
                step["output"] = {
                    "text": "ALWAYS FAIL",
                    "exec_success": False,
                    "test_result": {"exit_code": 1, "timed_out": False},
                }
            else:
                step["output"] = {"text": "attempted fix"}

        steps = [self._step("test"), self._step("fix"), self._step("doc")]
        context = self._run(steps, fake_exec)

        assert calls.count("test") == 4
        assert calls.count("fix") == 3
        assert steps[0]["status"] == STEP_STATE_FAILED
        assert steps[1]["status"] == STEP_STATE_SKIPPED
        assert steps[2]["status"] == STEP_STATE_SKIPPED
        assert context["meta"]["execution_state"] == "validation_failed"

    def test_test_without_execution_evidence_is_not_reported_as_passed_or_repaired(self):
        calls = []

        def fake_exec(task_id, step, events, context):
            calls.append(step["type"])
            step["output"] = {"text": "runner did not return a result"}

        steps = [self._step("test"), self._step("fix")]
        context = self._run(steps, fake_exec)

        assert calls == ["test"]
        assert steps[0]["status"] == STEP_STATE_FAILED
        assert steps[1]["status"] == STEP_STATE_SKIPPED
        assert context["meta"]["execution_state"] == "validation_failed"

    def test_test_waiting_for_authorization_stops_following_steps(self):
        calls = []

        def fake_exec(task_id, step, events, context):
            calls.append(step["type"])

        steps = [self._step("test"), self._step("fix")]
        context = self._run(
            steps,
            fake_exec,
            requires_authorization=True,
            context={"meta": {"proposed_test_command": "pytest"}},
        )

        assert calls == []
        assert steps[0]["status"] == STEP_STATE_AWAITING_AUTHORIZATION
        assert steps[1]["status"] == STEP_STATE_SKIPPED
        assert context["meta"]["execution_state"] == "awaiting_authorization"
        assert context["meta"]["authorization_requests"] == [{
            "type": "test",
            "command": "pytest",
            "status": "awaiting_host_policy",
        }]

    def test_no_retry_when_test_passes(self):
        calls = []

        def fake_exec(task_id, step, events, context):
            calls.append(step["type"])
            if step["type"] == "test":
                step["output"] = {"text": "PASS", "exec_success": True}

        steps = [self._step("test")]
        self._run(steps, fake_exec)

        assert calls == ["test"]
        assert steps[0]["status"] == STEP_STATE_COMPLETED