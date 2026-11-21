# python_worker/tests/test_g1037_contracts.py
"""G10.37 「删了旧文件却没重建」+ pytest exit 5 FAIL-OPEN 回归契约。

真实故障（shopflow_v16_1，16:46–16:53，427.75s）：
R5 四维全绿，R6 链路/执行/治理全绿、**质量红**，R7–R10 连锁前置失败。
工作区里 `backend/*` 全部齐备，唯独 `tests/test_orders.py` 消失，
本地 pytest `exit_code=5`（零用例被收集）。

根因链：
1. `cleanup_previous_generated` 在 `final_file_ops` 开头插入
   `delete tests/test_orders.py` 等 10 个删除 op；本轮 write_step
   只产出 7 个文件，没有重建测试文件。
2. `finalize_task` 的交付完整性守卫判漏项时只看磁盘 `exists()`，
   此刻上一遍的旧文件还在 → 误判「已交付」，不触发补齐。
3. Node 随后执行 delete，旧文件被删且没有 create 补回 → 零测试文件。
4. `delivery_gate._run_pytest()` 把 pytest exit 5 一律当
   「无测试用例，跳过」返回 True → 闸门把零测试工作区判绿并交付。

修复：被本轮 delete 命中的路径一律视为不存在；候选工作区存在
`test_*.py` 却收集不到用例时判失败，不再放行。
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker.agents.qwen import step_runner  # noqa: E402
from python_worker import delivery_gate  # noqa: E402
from python_worker.agents.qwen import qwen_api  # noqa: E402


def _context(tmp_path, ops, request=None):
    return {
        "meta": {
            "workspace_path": str(tmp_path),
            "user_request": request or (
                "1. backend/main.py\n"
                "7. tests/test_orders.py — pytest 覆盖所有 API 端点\n"
            ),
        },
        "final_file_ops": list(ops),
    }


def _fake_llm(monkeypatch, calls, raw=None):
    def _call(prompt, temperature=0.3):
        calls.append(prompt)
        return raw if raw is not None else (
            "# FILE: tests/test_orders.py\n"
            "def test_create_order():\n"
            "    assert True\n"
        )
    monkeypatch.setattr(qwen_api, "call_llm", _call)
    return calls


def test_delete_op_forces_regeneration_even_when_file_exists(tmp_path, monkeypatch):
    """v16 根因：磁盘上还留着旧文件，但本轮 delete 会删掉它。"""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_orders.py").write_text("old", encoding="utf-8")
    ctx = _context(tmp_path, [
        {"op": "delete", "path": "tests/test_orders.py", "content": ""},
        {"op": "create", "path": "backend/main.py", "content": "app = 1"},
    ])
    calls = _fake_llm(monkeypatch, [])
    report = step_runner._ensure_requested_deliverables(ctx, "write_code")
    assert "tests/test_orders.py" in report["missing"]
    assert "tests/test_orders.py" in report["recovered"]
    assert len(calls) == 1, "必须调用模型补齐被删掉的题面文件"
    created = [o for o in ctx["final_file_ops"]
               if o.get("op") != "delete" and o.get("path") == "tests/test_orders.py"]
    assert created and "def test_create_order" in created[0]["content"]
    assert ctx["meta"]["deliverable_guard"]["recovered"] == ["tests/test_orders.py"]


def test_delete_op_without_disk_file_also_recovers(tmp_path, monkeypatch):
    ctx = _context(tmp_path, [
        {"op": "delete", "path": "tests/test_orders.py", "content": ""},
    ])
    _fake_llm(monkeypatch, [])
    report = step_runner._ensure_requested_deliverables(ctx, "write_code")
    assert report["recovered"] == ["tests/test_orders.py"]


def test_existing_file_without_delete_is_not_regenerated(tmp_path, monkeypatch):
    """既有语义不变：没有 delete 且磁盘已有 → 不重复生成。"""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_orders.py").write_text("old", encoding="utf-8")
    ctx = _context(tmp_path, [
        {"op": "create", "path": "backend/main.py", "content": "app = 1"},
    ])
    calls = _fake_llm(monkeypatch, [])
    report = step_runner._ensure_requested_deliverables(ctx, "write_code")
    assert report["missing"] == []
    assert report["recovered"] == []
    assert calls == []


def test_create_op_satisfies_request_without_disk_file(tmp_path, monkeypatch):
    """本轮已 create 的文件不该因为磁盘还没有就被判漏。"""
    ctx = _context(tmp_path, [
        {"op": "delete", "path": "tests/test_orders.py", "content": ""},
        {"op": "create", "path": "tests/test_orders.py",
         "content": "def test_x(): pass"},
        {"op": "create", "path": "backend/main.py", "content": "app = 1"},
    ])
    calls = _fake_llm(monkeypatch, [])
    report = step_runner._ensure_requested_deliverables(ctx, "write_code")
    assert report["missing"] == []
    assert calls == []


class _Proc:
    def __init__(self, rc):
        self.returncode = rc
        self.stdout = "no tests ran"
        self.stderr = ""


def _mock_pytest(monkeypatch, rc):
    monkeypatch.setattr(delivery_gate.subprocess, "run",
                        lambda *a, **kw: _Proc(rc))


def test_exit5_with_test_module_is_failure(monkeypatch):
    """候选里有 test_*.py 却零收集 → 质量缺陷，不得放行。"""
    _mock_pytest(monkeypatch, 5)
    ok, out = delivery_gate._run_pytest(
        {"tests/test_orders.py": "def test_x(): pass",
         "backend/main.py": "app = 1"})
    assert ok is False
    assert "exit 5" in out


def test_exit5_with_only_conftest_still_skips(monkeypatch):
    """纯文档/配置轮次没有测试模块，保持既有跳过语义（R5 不回归）。"""
    _mock_pytest(monkeypatch, 5)
    ok, out = delivery_gate._run_pytest(
        {"tests/conftest.py": "import pytest",
         "docs/architecture_design.md": "# design"})
    assert ok is True
    assert "跳过" in out


def test_exit5_with_root_test_module_is_failure(monkeypatch):
    _mock_pytest(monkeypatch, 5)
    ok, _ = delivery_gate._run_pytest({"test_smoke.py": "x = 1"})
    assert ok is False


def test_exit0_still_passes(monkeypatch):
    _mock_pytest(monkeypatch, 0)
    ok, _ = delivery_gate._run_pytest(
        {"tests/test_orders.py": "def test_x(): pass"})
    assert ok is True


def test_static_contract_both_guards_present():
    src_runner = (_PROJECT_ROOT / "python_worker" / "agents" / "qwen" /
                  "step_runner.py").read_text(encoding="utf-8")
    src_gate = (_PROJECT_ROOT / "python_worker" / "delivery_gate.py").read_text(encoding="utf-8")
    assert '== "delete"' in src_runner
    assert "p in deleted or" in src_runner
    assert "has_test_module" in src_gate
