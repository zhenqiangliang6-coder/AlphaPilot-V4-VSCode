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

import os
import sys
import tempfile
import json
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# -------------------------------------------------------------------
# 路径准备 — 从项目根启动时 python_worker 是顶层包
# -------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # Copilot_Alphapilot/
sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker.agents.qwen.step_executor.test_step import _run_pytest
from python_worker.agents.qwen import qwen_worker_v2


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
    """L3: 验证 Worker test→fix→retest 闭环。"""

    @pytest.fixture
    def sandbox_ws(self):
        d = tempfile.mkdtemp(prefix="ap_retry_test_")
        yield d
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    # --------------------------------------------------------
    #  成功路径：test 失败 → fix → retest 通过 → skip chain fix
    # --------------------------------------------------------
    def test_retry_success_path(self, sandbox_ws):
        call_seq = []

        def fake_exec(task_id, step, events, context):
            st = step["type"]
            seq = len(call_seq) + 1
            call_seq.append((st, seq))

            # 前两次 test 调用失败，之后通过
            test_calls_so_far = sum(1 for s, _ in call_seq if s == "test")
            if st == "test":
                if test_calls_so_far <= 2:
                    step["output"] = {"text": "FAIL", "exec_success": False}
                else:
                    step["output"] = {"text": "PASS", "exec_success": True}
            else:
                step["output"] = {"text": f"ok:{st}"}

        with (
            patch.object(qwen_worker_v2, "MEMORY_ENABLED", False),
            patch.object(qwen_worker_v2, "check_stop_flag", return_value=False),
            patch.object(qwen_worker_v2, "stream_start"),
            patch.object(qwen_worker_v2, "stream_chunk"),
            patch.object(qwen_worker_v2, "execute_step", side_effect=fake_exec),
            patch.object(qwen_worker_v2, "requires_authorization_before_step", return_value=False),
        ):
            qwen_worker_v2.execute_task(
                "qwen_generate",
                {"prompt": "write a test success path", "workspace_path": sandbox_ws},
                f"test-{uuid.uuid4().hex[:6]}",
                [],
                [],
                {
                    "meta": {"workspace_path": sandbox_ws},
                    "final_file_ops": [],
                    "intermediate_results": [],
                    "tool_outputs": [],
                },
            )

        test_indices = [i for i, (s, _) in enumerate(call_seq) if s == "test"]
        fix_indices = [i for i, (s, _) in enumerate(call_seq) if s == "fix"]

        assert len(test_indices) >= 2, f"Expected >=2 test calls, got {call_seq}"
        assert len(fix_indices) >= 1, f"Expected >=1 fix calls, got {call_seq}"
        assert len(fix_indices) <= 2, f"Too many fix calls: {call_seq}"

    # --------------------------------------------------------
    #  失败路径：持续失败 → 3 次上限 → 退出不假报
    # --------------------------------------------------------
    def test_retry_failure_path_3_max(self, sandbox_ws):
        call_seq = []

        def always_fail_test(task_id, step, events, context):
            st = step["type"]
            call_seq.append(st)
            if st == "test":
                step["output"] = {"text": "ALWAYS FAIL", "exec_success": False}
            else:
                step["output"] = {"text": f"ok:{st}"}

        with (
            patch.object(qwen_worker_v2, "MEMORY_ENABLED", False),
            patch.object(qwen_worker_v2, "check_stop_flag", return_value=False),
            patch.object(qwen_worker_v2, "stream_start"),
            patch.object(qwen_worker_v2, "stream_chunk"),
            patch.object(qwen_worker_v2, "execute_step", side_effect=always_fail_test),
            patch.object(qwen_worker_v2, "requires_authorization_before_step", return_value=False),
        ):
            try:
                qwen_worker_v2.execute_task(
                    "qwen_generate",
                    {"prompt": "write a test failure path", "workspace_path": sandbox_ws},
                    f"test-{uuid.uuid4().hex[:6]}",
                    [],
                    [],
                    {
                        "meta": {"workspace_path": sandbox_ws},
                        "final_file_ops": [],
                        "intermediate_results": [],
                        "tool_outputs": [],
                    },
                )
            except Exception:
                pass

        test_calls = call_seq.count("test")
        fix_calls = call_seq.count("fix")
        assert test_calls == 4, f"Expected 4 test calls (1 initial + 3 retries), got seq: {call_seq}"
        assert fix_calls == 4, f"Expected 4 fix calls (3 retries + 1 chain), got seq: {call_seq}"

    # --------------------------------------------------------
    #  正常路径：test 一开始就通过
    # --------------------------------------------------------
    def test_no_retry_when_pass(self, sandbox_ws):
        call_seq = []

        def all_pass(task_id, step, events, context):
            st = step["type"]
            call_seq.append(st)
            if st == "test":
                step["output"] = {"text": "ok", "exec_success": True}
            else:
                step["output"] = {"text": f"ok:{st}"}

        with (
            patch.object(qwen_worker_v2, "MEMORY_ENABLED", False),
            patch.object(qwen_worker_v2, "check_stop_flag", return_value=False),
            patch.object(qwen_worker_v2, "stream_start"),
            patch.object(qwen_worker_v2, "stream_chunk"),
            patch.object(qwen_worker_v2, "execute_step", side_effect=all_pass),
            patch.object(qwen_worker_v2, "requires_authorization_before_step", return_value=False),
        ):
            qwen_worker_v2.execute_task(
                "qwen_generate",
                {"prompt": "write a all pass path", "workspace_path": sandbox_ws},
                f"test-{uuid.uuid4().hex[:6]}",
                [],
                [],
                {
                    "meta": {"workspace_path": sandbox_ws},
                    "final_file_ops": [],
                    "intermediate_results": [],
                    "tool_outputs": [],
                },
            )

        # 每个步骤只执行一次
        assert call_seq.count("test") == 1, f"Expected 1 test call, got {call_seq}"
        assert call_seq.count("fix") == 1, f"Expected 1 fix call, got {call_seq}"