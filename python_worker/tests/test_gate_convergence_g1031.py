# python_worker/tests/test_gate_convergence_g1031.py
"""G10.31 交付闸门收敛与每遍同构基线契约。

v10 第 1 遍 R8 的两个系统性缺陷：
1. LLM 补丁让失败数 4 → 5 就判 worsening 止损，5 轮预算只用 1 轮；
2. 分层收敛「保留新增文件、回滚既有文件修改」留下依赖注册入口的
   孤儿文件，真实工作区 10 个 404，连带 R9/R10 前置条件失败。

外加「连续三遍」的同构基线：一遍终态不能成为下一遍起点。
"""

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker import delivery_gate as dg  # noqa: E402
from python_worker.tests import test_observe_task_system as obs  # noqa: E402


BASE = {
    "tests/test_ok.py": "def test_ok():\n    assert True\n",
    "backend/main.py": "app = object()\n",
}
BAD_NEW = "tests/test_new.py"
BAD_OUTPUT = ("FAILED tests/test_new.py::test_bad - AssertionError\n"
              "1 failed in 0.2s")
WORSE_OUTPUT = ("FAILED tests/test_new.py::test_bad - AssertionError\n"
                "FAILED tests/test_ok.py::test_ok - AssertionError\n"
                "2 failed in 0.2s")


def _ctx(ops=None):
    return {
        "meta": {"workspace_path": "C:/tmp/ws", "user_request": "增加库存模块"},
        "final_file_ops": ops if ops is not None else [
            {"op": "create", "path": BAD_NEW,
             "content": "def test_bad():\n    assert False\n"},
            {"op": "modify", "path": "backend/main.py",
             "content": "app = object()\nregister_inventory()\n"},
        ],
    }


def test_layered_convergence_full_rollback_when_kept_files_break_baseline(monkeypatch):
    """交付清单让基线从绿变红 → 连新增文件一起回滚，不留孤儿产物。"""
    monkeypatch.setattr(dg, "snapshot_workspace", lambda ws: dict(BASE))
    monkeypatch.setattr(dg, "_MAX_REPAIR_ROUNDS", 0)

    def fake_pytest(files):
        if set(files) == set(BASE):
            return True, ""                       # 基线绿
        if "register_inventory" in files.get("backend/main.py", ""):
            return False, BAD_OUTPUT              # full（含入口联动）: 1 failed
        return False, WORSE_OUTPUT                # kept（孤儿态）: 2 failed

    monkeypatch.setattr(dg, "_run_pytest", fake_pytest)
    ctx = _ctx()
    result = dg.gate(ctx, "incremental_feature")
    assert result["ran"] is True
    assert result["full_rollback"] is True
    assert result["partial_delivery"] is False
    assert result["kept_new_files"] == []
    assert all(op.get("_internal") for op in ctx["final_file_ops"])
    assert "全量回滚" in result["reason"]


def test_layered_convergence_keeps_new_files_when_baseline_stays_green(monkeypatch):
    """新增文件自洽时不触发全量回滚，原有分层收敛语义保留。"""
    monkeypatch.setattr(dg, "snapshot_workspace", lambda ws: dict(BASE))
    monkeypatch.setattr(dg, "_MAX_REPAIR_ROUNDS", 0)

    def fake_pytest(files):
        # 新增文件的坏测试在候选里挂，但交付清单里不再包含它时基线仍绿
        return True, ""

    monkeypatch.setattr(dg, "_run_pytest", fake_pytest)
    ctx = _ctx([{"op": "create", "path": "backend/models/extra.py",
                 "content": "X = 1\n"}])
    result = dg.gate(ctx, "incremental_feature")
    # 入口 pytest 即绿 → 直接走 _finalize_verified_pass，不进分层收敛
    assert result["passed"] is True
    assert result.get("full_rollback") is not True


def test_worsening_patch_is_reverted_and_budget_continues(monkeypatch):
    """恶化补丁被撤销，剩余修复预算继续用于异策略轮次。"""
    monkeypatch.setattr(dg, "snapshot_workspace", lambda ws: dict(BASE))
    monkeypatch.setattr(dg, "_MAX_REPAIR_ROUNDS", 3)
    monkeypatch.setattr(dg, "_repair_prompt", lambda *a, **k: "ignored")
    monkeypatch.setattr(dg, "_call_repair_llm",
                        lambda *a, **k: "PATCH")
    monkeypatch.setattr(
        "python_worker.file_ops.parse_fileops_v3",
        lambda reply: [{"path": "backend/main.py",
                        "content": "app = object()\npatched = True\n"}])
    monkeypatch.setattr(dg, "_retry_with_deterministic_fix",
                        lambda cand, out, fixes: (cand, False, out))
    monkeypatch.setattr(dg, "_finalize_verified_pass", lambda *a, **k: True)

    calls = {"n": 0}

    def fake_pytest(files):
        calls["n"] += 1
        if calls["n"] == 1:
            return False, BAD_OUTPUT          # 入口：1 failed
        if calls["n"] == 2:
            return False, WORSE_OUTPUT        # 第 1 轮补丁后：2 failed（恶化）
        if files == BASE or set(files) == set(BASE):
            return True, ""                   # 基线绿
        return False, BAD_OUTPUT

    monkeypatch.setattr(dg, "_run_pytest", fake_pytest)
    result = dg.gate(_ctx(), "incremental_feature")
    assert result["ran"] is True
    assert any(e.get("reverted") for e in result["history"]), (
        "恶化补丁应被撤销并记入 history")
    assert result["rounds"] >= 2, "撤销后应继续使用剩余预算"


def test_pass_baseline_is_recorded_then_restored(tmp_path, monkeypatch):
    """首遍固化基线，后续遍恢复到同一状态（含删除新增文件）。"""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "backend").mkdir()
    (ws / "backend" / "main.py").write_text("app = 1\n", encoding="utf-8")
    (ws / "tests").mkdir()
    (ws / "tests" / "test_ok.py").write_text(
        "def test_ok(): pass\n", encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    monkeypatch.setattr(obs, "DEFAULT_WORKSPACE", str(ws))
    monkeypatch.setattr(obs, "_SHOPFLOW_BASELINE", baseline)

    obs._reset_pass_baseline()
    assert baseline.exists()
    snap = json.loads(baseline.read_text(encoding="utf-8"))
    assert "backend/main.py" in snap

    (ws / "backend" / "main.py").write_text("app = 999\n", encoding="utf-8")
    (ws / "tests" / "test_new.py").write_text(
        "def test_new(): pass\n", encoding="utf-8")

    obs._reset_pass_baseline()
    assert (ws / "backend" / "main.py").read_text(encoding="utf-8") == "app = 1\n"
    assert not (ws / "tests" / "test_new.py").exists()
