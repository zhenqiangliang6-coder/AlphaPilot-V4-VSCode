# -*- coding: utf-8 -*-
"""回归契约：交付前隔离沙箱自检（Shadow Verification）。

真实故障（2026-11-14 ShopFlow run9 / run10）：
  R6 生成的代码与它自己生成的测试不自洽 ——
    OrderCreate.user_id: int 但测试传字符串 → 422
    relationship("OrderItem") 引用未定义 ORM 类 → SQLAlchemy 解析失败
  `test` 步骤因 awaiting_authorization 被 defer，既有 fix→retest 闭环从未执行，
  脏文件直接落盘，R6–R10 连锁失败。静态语法门控抓不到这类运行时错误。

修复：python_worker/shadow_verify.py + step_runner.finalize_task() v3.6 集成。
本契约锁死触发范围、路径安全、真实沙箱执行、修复闭环与「不采纳坏修复」。
"""
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from python_worker import shadow_verify

_ROOT = Path(__file__).resolve().parents[2]
_RUNNER = _ROOT / "python_worker" / "agents" / "qwen" / "step_runner.py"


def _ops(app_body="    return a - b\n"):
    return [
        {"op": "create", "path": "app.py",
         "content": "def add(a, b):\n" + app_body},
        {"op": "create", "path": "tests/test_app.py",
         "content": "from app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"},
    ]


def test_should_verify_only_for_full_project_write_code():
    assert shadow_verify.should_verify("write_code", _ops())
    assert not shadow_verify.should_verify("architecture", _ops())
    assert not shadow_verify.should_verify("refactor", _ops())
    assert not shadow_verify.should_verify("fix_code", _ops())
    assert not shadow_verify.should_verify(
        "write_code", [{"op": "create", "path": "app.py", "content": "x = 1"}]
    )
    assert not shadow_verify.should_verify(
        "write_code", [{"op": "create", "path": "tests/test_app.py", "content": "x = 1"}]
    )


def test_materialize_rejects_path_traversal_and_absolute_paths():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ops = [
            {"op": "create", "path": "ok/app.py", "content": "x = 1\n"},
            {"op": "create", "path": "../outside.py", "content": "x = 2\n"},
            {"op": "create", "path": "C:/Windows/evil.py", "content": "x = 3\n"},
            {"op": "create", "path": "/etc/evil.py", "content": "x = 4\n"},
            {"op": "delete", "path": "removed.py", "content": "x = 5\n"},
        ]
        assert shadow_verify._materialize(ops, root) == 1
        assert (root / "ok" / "app.py").read_text(encoding="utf-8") == "x = 1\n"
        assert not (root / "outside.py").exists()
        assert not (root / "removed.py").exists()


def test_run_pytest_reports_real_pass_and_failure():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        shadow_verify._materialize(_ops("    return a + b\n"), root)
        ok, out = shadow_verify._run_pytest(root)
        assert ok, out

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        shadow_verify._materialize(_ops(), root)  # 故意写错
        ok, out = shadow_verify._run_pytest(root)
        assert not ok
        assert "test_add" in out or "assert" in out


def test_verify_and_repair_fixes_generated_code_in_place(monkeypatch):
    """第一轮失败 → 模型修复 app.py → 第二轮通过；content 必须被原地改写。"""
    import python_worker.agents.qwen.qwen_api as api

    monkeypatch.setattr(
        api, "call_llm",
        lambda prompt, temperature=0.3: "# FILE: app.py\ndef add(a, b):\n    return a + b\n",
    )
    file_ops = _ops()
    ctx = {"final_file_ops": file_ops, "meta": {"user_request": "实现 add"}}
    result = shadow_verify.verify_and_repair(ctx, "write_code")

    assert result["ran"] is True
    assert result["passed"] is True, result
    assert result["rounds"] == 2
    assert "app.py" in result["repaired_files"]
    assert "return a + b" in file_ops[0]["content"]


def test_verify_rejects_repair_that_introduces_syntax_error(monkeypatch):
    """修复轮次不得把新的语法错误带进交付内容。"""
    import python_worker.agents.qwen.qwen_api as api

    monkeypatch.setattr(
        api, "call_llm",
        lambda prompt, temperature=0.3: (
            "# FILE: app.py\ndef add(a, b):\n    return a + b\n"
            "Optimized the implementation for production readiness and reliability.\n"
        ),
    )
    ctx = {"final_file_ops": _ops(), "meta": {"user_request": "实现 add"}}
    result = shadow_verify.verify_and_repair(ctx, "write_code")
    assert result["ran"] is True
    assert result["repaired_files"] == []
    assert "未产出有效改动" in result.get("error", "")


def test_verify_is_skipped_for_non_write_code():
    ctx = {"final_file_ops": _ops(), "meta": {}}
    assert shadow_verify.verify_and_repair(ctx, "architecture") == {
        "ran": False, "passed": False, "rounds": 0, "repaired_files": [],
        "block_delivery": False,
    }


def test_finalize_task_integrates_shadow_verify():
    src = _RUNNER.read_text(encoding="utf-8")
    assert "from ...shadow_verify import verify_and_repair" in src
    # G10.15：集成点改为「先取证、再据 block_delivery 做 FAIL-CLOSED」
    assert "_sv = verify_and_repair(context, intent)" in src
    assert 'context["meta"]["shadow_verify"] = _sv' in src
    assert '_sv.get("block_delivery")' in src
    assert 'context["meta"]["delivery_blocked"]' in src
    assert "交付闸门 FAIL-CLOSED" in src
