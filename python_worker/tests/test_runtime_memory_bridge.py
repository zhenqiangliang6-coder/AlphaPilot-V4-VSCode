# -*- coding: utf-8 -*-
"""
tests/test_runtime_memory_bridge.py
P2-3「Runtime → ConversationTurn 桥接，根除 status="success" 硬编码」红线基线（Eval Harness）

用途
====
锁定「生产 Worker 记忆保存链路」的安全契约：worker_runtime.save_worker_memory
不再无条件硬编码 status="success"，而是从 steps 推导真实 outcome。

设计原则（延续 P0/P1/P2-1/P2-2「先基线后实现」）：
1. 失败任务 → result["status"] 必须映射为 "failed"，不得硬编码 success。
2. 无错误/无失败标记的任务 → result["status"] 映射为 "success"（正向兼容）。
3. 失败内容原样透传 → 持久化层不得丢弃错误文本。

安全指标（P2-3 实施后必须恒为 0）：
  M-R1 失败任务被误标为 success 的次数  failed_task_marked_success = 0
"""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # Copilot_Alphapilot/
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


@pytest.fixture
def captured_save(monkeypatch):
    """Monkeypatch save_task_memories，捕获调用时的 kwargs。"""
    from python_worker import worker_runtime
    captured = []

    def _capture(*args, **kwargs):
        captured.append((args, kwargs))
        return True

    monkeypatch.setattr(worker_runtime, "save_task_memories", _capture)
    return captured


class TestRuntimeStatusBridge:
    """从 steps 推导真实 status，根除硬编码 success。"""

    def test_R1_failure_step_produces_status_failed(self, captured_save):
        """含 error 字段的 step → 最终传给持久化层 result["status"] = "failed"。"""
        from python_worker.worker_runtime import save_worker_memory

        save_worker_memory(
            user_id="u-r1",
            task_id="t-r1",
            task_type="chat",
            intent="fix_code",
            result="任务执行失败：超时",
            steps=[{"type": "fix", "output": "尝试修复"}, {"type": "error", "output": "超时"}],
            context={"meta": {"user_request": "修复 bug", "workspace_path": "/tmp"}},
        )

        _, kwargs = captured_save[0]
        result_dict = kwargs["result"]
        assert result_dict["status"] == "failed", "含 error step 的失败任务不得硬编码 success"

    def test_R2_clean_steps_produces_status_success(self, captured_save):
        """所有 steps 无错误标记 → 正向兼容：status = "success"。"""
        from python_worker.worker_runtime import save_worker_memory

        save_worker_memory(
            user_id="u-r2",
            task_id="t-r2",
            task_type="write_code",
            intent="write_code",
            result="生成代码完成",
            steps=[{"type": "plan", "output": "拆解任务"}, {"type": "write", "output": "写入文件"}],
            context={"meta": {"user_request": "写代码", "workspace_path": "/tmp"}},
        )

        _, kwargs = captured_save[0]
        result_dict = kwargs["result"]
        assert result_dict["status"] == "success", "无错误的任务正向兼容映射为 success"

    def test_R3_failure_content_preserved(self, captured_save):
        """失败任务的 result 内容原样透传，不得被硬编码丢弃。"""
        from python_worker.worker_runtime import save_worker_memory

        error_text = "连接数据库超时：pool exhausted after 30s"
        save_worker_memory(
            user_id="u-r3",
            task_id="t-r3",
            task_type="explain_and_fix",
            intent="fix_code",
            result=error_text,
            steps=[{"type": "error", "output": error_text}],
            context={"meta": {"user_request": "修复数据库问题", "workspace_path": "/tmp"}},
        )

        _, kwargs = captured_save[0]
        result_dict = kwargs["result"]
        assert result_dict["status"] == "failed"
        assert error_text in result_dict["content"], "失败内容必须原样透传"

    def test_R4_empty_steps_produces_status_success(self, captured_save):
        """边界兼容：空 steps → 视为无错误，映射为 success。"""
        from python_worker.worker_runtime import save_worker_memory

        save_worker_memory(
            user_id="u-r4",
            task_id="t-r4",
            task_type="chat",
            intent="chat",
            result="好的，收到",
            steps=[],
            context={"meta": {"user_request": "你好", "workspace_path": "/tmp"}},
        )

        _, kwargs = captured_save[0]
        result_dict = kwargs["result"]
        assert result_dict["status"] == "success"

    def test_R5_error_field_in_step_produces_status_failed(self, captured_save):
        """step 内含非空 error 字段（非 type=="error"）→ status = "failed"。"""
        from python_worker.worker_runtime import save_worker_memory

        save_worker_memory(
            user_id="u-r5",
            task_id="t-r5",
            task_type="compile",
            intent="fix_code",
            result="编译失败",
            steps=[{"type": "compile", "error": "SyntaxError: invalid syntax"}],
            context={"meta": {"user_request": "修复编译", "workspace_path": "/tmp"}},
        )

        _, kwargs = captured_save[0]
        result_dict = kwargs["result"]
        assert result_dict["status"] == "failed", "含 error 字段的 step 必须推导为 failed"