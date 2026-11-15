# python_worker/tests/test_delivery_gate.py
"""交付闸门回归契约（G10.15）。

覆盖：失败签名与自适应预算、确定性幻觉导入修复、事务式候选工作区
pytest、LLM 异策略修复、FAIL-CLOSED 决策、无基线 FAIL-OPEN。
"""
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker import delivery_gate as dg  # noqa: E402


# ── 失败签名与进展检测 ───────────────────────────────────────────

def test_failure_signature_extracts_tests_and_error_types():
    out = ("FAILED tests/test_a.py::test_one - KeyError: 'id'\n"
           "FAILED tests/test_a.py::test_two - KeyError: 'id'\n"
           "1 warning, 2 failed in 0.3s")
    sig = dg.failure_signature(out)
    assert sig["failed_count"] == 2
    assert "KeyError" in sig["error_types"]
    assert len(sig["failed_tests"]) == 2
    assert sig["sig"]


def test_progress_converging_stalled_worsening():
    a = {"sig": "aaa", "failed_count": 8, "error_types": ["KeyError"]}
    b = {"sig": "bbb", "failed_count": 3, "error_types": ["KeyError"]}
    assert dg.progress(None, a) == "first"
    assert dg.progress(a, b) == "converging"
    assert dg.progress(a, a) == "stalled"
    assert dg.progress(a, {"sig": "ccc", "failed_count": 12,
                           "error_types": ["KeyError"]}) == "worsening"


def test_import_crash_to_quantified_failures_is_converging():
    """run1d：ImportError 无法收集(-1) → 4 failed，是收敛不是停滞。"""
    prev = {"sig": "aaa", "failed_count": -1,
            "error_types": ["ImportError"]}
    cur = {"sig": "bbb", "failed_count": 4,
           "error_types": ["AssertionError"]}
    assert dg.progress(prev, cur) == "converging"

# ── 确定性符号解析修复 ───────────────────────────────────────────

def test_nonexistent_module_is_redirected_to_symbol_owner():
    files = {
        "backend/__init__.py": "",
        "backend/database.py": "Base = object()\n",
        "backend/models/__init__.py": "from backend.models.base import Base\n",
    }
    fixed, fixes = dg.resolve_internal_imports(files)
    assert "from backend.database import Base" in fixed["backend/models/__init__.py"]
    assert "backend.models.base" not in fixed["backend/models/__init__.py"]
    assert fixes and "backend.models.base" in fixes[0]


def test_nonexistent_symbol_is_dropped_or_redirected():
    files = {
        "backend/__init__.py": "",
        "backend/models/order.py": "class Order:\n    pass\n",
        "tests/test_inventory.py": (
            "from backend.models.order import Order, OrderItem\n"
            "def test_x():\n    assert Order\n"),
    }
    fixed, fixes = dg.resolve_internal_imports(files)
    line = fixed["tests/test_inventory.py"].splitlines()[0]
    assert "OrderItem" not in line
    assert "from backend.models.order import Order" in line
    assert fixes


def test_package_submodule_import_is_preserved():
    """from 包 import 子模块 是合法写法，不能被当成不存在的符号删掉。"""
    files = {
        "backend/__init__.py": "",
        "backend/routers/__init__.py": "",
        "backend/routers/orders.py": "router = 1\n",
        "backend/routers/inventory.py": "router = 2\n",
        "backend/main.py": "from backend.routers import orders, inventory\n",
    }
    fixed, fixes = dg.resolve_internal_imports(files)
    assert "from backend.routers import orders, inventory" in fixed["backend/main.py"]
    assert fixes == []


def test_ambiguous_symbol_prefers_database_over_main():
    """Base 有多个定义者时选 database（而不是入口 main），不得直接丢弃。"""
    files = {
        "backend/__init__.py": "",
        "backend/database.py": "Base = object()\n",
        "backend/main.py": "Base = object()\n",
        "backend/models/__init__.py": "from backend.models.base import Base\n",
    }
    fixed, _ = dg.resolve_internal_imports(files)
    assert "from backend.database import Base" in fixed["backend/models/__init__.py"]

def test_external_imports_are_untouched():
    files = {
        "backend/__init__.py": "",
        "backend/a.py": "from typing import List\nimport sqlalchemy\n"
                        "from fastapi import APIRouter, HTTPException\n",
    }
    fixed, fixes = dg.resolve_internal_imports(files)
    assert fixed["backend/a.py"] == files["backend/a.py"]
    assert fixes == []


# ── 快照与候选工作区 ─────────────────────────────────────────────

def test_snapshot_and_candidate(tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "a.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / ".venv" / "lib").mkdir(parents=True)
    (tmp_path / ".venv" / "lib" / "junk.py").write_text("JUNK", encoding="utf-8")
    snap = dg.snapshot_workspace(str(tmp_path))
    assert "backend/a.py" in snap
    assert not any(k.startswith(".venv") for k in snap)
    cand = dg.build_candidate(snap, [
        {"op": "create", "path": "backend/b.py", "content": "Y = 2\n"},
        {"op": "create", "path": "../../escape.py", "content": "bad"},
        {"op": "create", "path": "backend/a.py", "content": "X = 9\n"},
    ])
    assert cand["backend/b.py"] == "Y = 2\n"
    assert cand["backend/a.py"] == "X = 9\n"
    assert not any("escape" in k for k in cand)


def _ws_with_baseline(tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "backend" / "ok.py").write_text("Base = object()\nVALUE = 1\n",
                                                encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text(
        "from backend.broken import VALUE\n\ndef test_ok():\n    assert VALUE == 1\n",
        encoding="utf-8")
    return tmp_path


def _ctx(ws, ops):
    return {"meta": {"workspace_path": str(ws), "user_request": "增量开发"},
            "final_file_ops": ops}


def test_gate_deterministic_repair_passes(tmp_path):
    """幻觉导入被确定性重定向后，候选工作区 pytest 通过并回写 file_ops。"""
    ws = _ws_with_baseline(tmp_path)
    op = {"op": "create", "path": "backend/broken.py",
          "content": "from backend.models.base import Base\nVALUE = 1\n"}
    ctx = _ctx(ws, [op])
    out = dg.gate(ctx, "write_code")
    assert out["ran"] and out["passed"]
    assert out["rounds"] == 0  # 确定性修复，不消耗 LLM 轮次
    assert out["fixes"]
    assert "from backend.ok import Base" in op["content"] or "Base" not in op["content"]


def test_gate_failure_uses_partial_delivery(tmp_path, monkeypatch):
    """LLM 修不好 → 分层收敛：保留新增文件、回滚既有文件修改。"""
    ws = _ws_with_baseline(tmp_path)
    (ws / "backend" / "broken.py").write_text("VALUE = 1\n", encoding="utf-8")
    bad = {"op": "create", "path": "tests/test_bad.py",
           "content": "def test_bad():\n    assert False\n"}
    existing = {"op": "modify", "path": "backend/broken.py", "content": "VALUE = 99\n"}
    ctx = _ctx(ws, [bad, existing])
    monkeypatch.setattr("python_worker.agents.qwen.qwen_api.call_llm",
                        lambda *a, **k: "")
    out = dg.gate(ctx, "write_code")
    assert out["ran"] and not out["passed"]
    assert out["partial_delivery"] is True
    assert not out["block_delivery"]  # gate 已完成收敛，不需要上游全量丢弃
    assert "tests/test_bad.py" in out["kept_new_files"]
    assert "backend/broken.py" in out["dropped_existing"]
    assert all(str(o.get("path")) != "backend/broken.py"
               for o in ctx["final_file_ops"])
    assert out["history"] and out["history"][0]["progress"] == "first"


def test_gate_llm_repair_can_pass(tmp_path, monkeypatch):
    """异策略 LLM 修复生效后通过闸门，并回写修复内容。"""
    ws = _ws_with_baseline(tmp_path)
    (ws / "backend" / "broken.py").write_text("VALUE = 1\n", encoding="utf-8")
    bad = {"op": "create", "path": "tests/test_bad.py",
           "content": "def test_bad():\n    assert False\n"}
    ctx = _ctx(ws, [bad])
    monkeypatch.setattr("python_worker.agents.qwen.qwen_api.call_llm",
                        lambda *a, **k: "# FILE: tests/test_bad.py")
    monkeypatch.setattr("python_worker.file_ops.parse_fileops_v3",
                        lambda _r: [{"op": "modify", "path": "tests/test_bad.py",
                                     "content": "def test_bad():\n    assert True\n"}])
    out = dg.gate(ctx, "write_code")
    assert out["passed"] and out["rounds"] == 1
    assert "assert True" in bad["content"]
    assert not out["block_delivery"]


def test_gate_fail_open_without_baseline(tmp_path):
    """既无 .py 基线、本次也不产出 tests/ → 闸门不启用，不阻断。"""
    (tmp_path / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    ctx = _ctx(tmp_path, [{"op": "create", "path": "backend/a.py",
                           "content": "X = 1\n"}])
    out = dg.gate(ctx, "write_code")
    assert not out["ran"] and not out["block_delivery"]


def test_gate_runs_for_from_zero_project_with_generated_tests(tmp_path):
    """G10.17：R6 从零建项目但本次自带 tests/ → 闸门启用并验证候选工作区。"""
    (tmp_path / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    ops = [
        {"op": "create", "path": "backend/__init__.py", "content": ""},
        {"op": "create", "path": "backend/value.py", "content": "VALUE = 1\n"},
        {"op": "create", "path": "tests/test_value.py",
         "content": "from backend.value import VALUE\n\n\ndef test_value():\n"
                    "    assert VALUE == 1\n"},
    ]
    ctx = _ctx(tmp_path, ops)
    out = dg.gate(ctx, "write_code")
    assert out["ran"] and out["passed"]
    assert not out["block_delivery"]
    assert out["rounds"] == 0  # 一次候选 pytest 通过，不消耗 LLM 轮次


def test_gate_from_zero_failure_keeps_all_new_files(tmp_path, monkeypatch):
    """G10.17：从零项目闸门失败时分层收敛不得把新增文件全丢了。"""
    (tmp_path / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    ops = [
        {"op": "create", "path": "backend/__init__.py", "content": ""},
        {"op": "create", "path": "backend/value.py", "content": "VALUE = 1\n"},
        {"op": "create", "path": "tests/test_value.py",
         "content": "def test_value():\n    assert False\n"},
    ]
    ctx = _ctx(tmp_path, ops)
    monkeypatch.setattr("python_worker.agents.qwen.qwen_api.call_llm",
                        lambda *a, **k: "")
    out = dg.gate(ctx, "write_code")
    assert out["ran"] and not out["passed"]
    assert out["partial_delivery"] and not out["block_delivery"]
    assert "tests/test_value.py" in out["kept_new_files"]
    assert "backend/value.py" in out["kept_new_files"]
    assert len(ctx["final_file_ops"]) == 3


def test_apply_back_never_attaches_content_to_delete_op():
    """G10.19：清理用的 delete op 不能承载修复内容（Node 侧会拒绝执行）。"""
    delete_op = {"op": "delete", "path": "backend/routers/orders.py",
                 "content": "", "reason": "清理上次生成的临时文件"}
    ctx = {"final_file_ops": [delete_op]}
    candidate = {"backend/routers/orders.py": "# repaired\nVALUE = 2\n"}
    base = {"backend/routers/orders.py": "VALUE = 1\n"}
    written = dg._apply_back(ctx, candidate, base)
    assert written == 1
    assert delete_op.get("content") in ("", None), "修复内容绝不能挂到 delete op"
    writable = [o for o in ctx["final_file_ops"]
                if o.get("op") in dg._WRITABLE_OPS
                and o.get("path") == "backend/routers/orders.py"]
    assert len(writable) == 1
    assert "# repaired" in writable[0]["content"]
    assert writable[0]["op"] == "modify"


def test_apply_back_reuses_existing_writable_op():
    """正常 create op 仍原地更新，不产生重复写操作。"""
    op = {"op": "create", "path": "backend/a.py", "content": "X = 1\n"}
    ctx = {"final_file_ops": [{"op": "delete", "path": "backend/a.py",
                               "content": ""}, op]}
    dg._apply_back(ctx, {"backend/a.py": "X = 2\n"}, {"backend/a.py": "X = 0\n"})
    assert op["content"] == "X = 2\n"
    assert len([o for o in ctx["final_file_ops"] if o.get("path") == "backend/a.py"]) == 2


def test_gate_from_zero_repair_lands_in_writable_op(tmp_path, monkeypatch):
    """G10.19 集成：闸门 LLM 修复既有路径时，落盘清单里必须有可写 op。"""
    (tmp_path / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    delete_op = {"op": "delete", "path": "backend/value.py", "content": ""}
    ops = [
        delete_op,
        {"op": "create", "path": "backend/__init__.py", "content": ""},
        {"op": "create", "path": "backend/value.py", "content": "VALUE = 1\n"},
        {"op": "create", "path": "tests/test_value.py",
         "content": "from backend.value import VALUE\n\n\ndef test_value():\n"
                    "    assert VALUE == 2\n"},
    ]
    ctx = _ctx(tmp_path, ops)
    monkeypatch.setattr("python_worker.agents.qwen.qwen_api.call_llm",
                        lambda *a, **k: "# FILE: backend/value.py")
    monkeypatch.setattr("python_worker.file_ops.parse_fileops_v3",
                        lambda _r: [{"op": "modify", "path": "backend/value.py",
                                     "content": "VALUE = 2\n"}])
    out = dg.gate(ctx, "write_code")
    assert out["ran"] and out["passed"] and out["rounds"] == 1
    assert delete_op.get("content") in ("", None)
    landed = [o for o in ctx["final_file_ops"]
              if o.get("op") in dg._WRITABLE_OPS
              and o.get("path") == "backend/value.py" and o.get("content")]
    assert landed and "VALUE = 2" in landed[-1]["content"], \
        "闸门修复后的源码必须落在可写 op 上"


def _mismatch_ws(tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "backend" / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_value.py").write_text(
        "from backend.value import VALUE\n\n\ndef test_value():\n"
        "    assert VALUE == 2\n", encoding="utf-8")
    return tmp_path


def test_finalize_verified_pass_accepts_real_delivery(tmp_path):
    """G10.19：_apply_back 修好后，落盘清单复验通过 → 准入。"""
    ws = _mismatch_ws(tmp_path)
    base = dg.snapshot_workspace(str(ws))
    ctx = {"final_file_ops": [
        {"op": "delete", "path": "backend/value.py", "content": ""},
        {"op": "delete", "path": "tests/test_value.py", "content": ""},
    ]}
    candidate = dict(base)
    candidate["backend/value.py"] = "VALUE = 2\n"
    result = {"written": 0}
    assert dg._finalize_verified_pass(ctx, result, candidate, base, "ok") is True
    assert result["passed"]


def test_finalize_verified_pass_rejects_unwritable_payload(tmp_path, monkeypatch):
    """G10.19：候选绿但落盘清单仍是旧版（旧 _apply_back bug）→ 拒绝准入。"""
    ws = _mismatch_ws(tmp_path)
    base = dg.snapshot_workspace(str(ws))
    ctx = {"final_file_ops": [
        {"op": "delete", "path": "backend/value.py", "content": ""},
        {"op": "delete", "path": "tests/test_value.py", "content": ""},
    ]}

    def buggy_apply_back(context, cand, _base):
        for op in context["final_file_ops"]:
            if op.get("path") in cand:
                op["content"] = cand[op["path"]]
        return len(cand)

    monkeypatch.setattr(dg, "_apply_back", buggy_apply_back)
    candidate = dict(base)
    candidate["backend/value.py"] = "VALUE = 2\n"
    result = {"written": 0}
    assert dg._finalize_verified_pass(ctx, result, candidate, base, "ok") is False
    assert not result["passed"]
    assert "回写后复验失败" in result["reason"]
    assert result["delivery_mismatch"]


def test_repair_llm_transient_error_is_retried(monkeypatch, tmp_path):
    """G10.20：一次网络瞬断不该让闸门判死，退避后重试应继续自愈。"""
    monkeypatch.setattr(dg.time, "sleep", lambda _s: None)
    calls = []

    def fake_llm(prompt, temperature=0.3):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("[API 调用失败: 所有模型不可用 - ConnectTimeoutError]")
        return "# FILE: tests/test_bad.py"

    monkeypatch.setattr("python_worker.agents.qwen.qwen_api.call_llm", fake_llm)
    monkeypatch.setattr("python_worker.file_ops.parse_fileops_v3",
                        lambda _r: [{"op": "modify", "path": "tests/test_bad.py",
                                     "content": "def test_bad():\n    assert True\n"}])
    ws = _ws_with_baseline(tmp_path)
    bad = {"op": "create", "path": "tests/test_bad.py",
           "content": "def test_bad():\n    assert False\n"}
    out = dg.gate(_ctx(ws, [bad]), "write_code")
    assert out["passed"] and len(calls) == 2


def test_repair_llm_logic_error_is_not_retried(monkeypatch):
    """非网络错误（逻辑/配额类）立即抛出，不白烧额度。"""
    monkeypatch.setattr(dg.time, "sleep", lambda _s: None)
    calls = []

    def fake(*_a, **_k):
        calls.append(1)
        raise ValueError("bad prompt")

    with pytest.raises(ValueError):
        dg._call_repair_llm("p", 0.1, fake)
    assert len(calls) == 1
    assert dg._is_transient_llm_error(RuntimeError("ConnectTimeout")) is True
    assert dg._is_transient_llm_error(ValueError("bad prompt")) is False


def test_gate_transient_failure_skips_round_not_abort(monkeypatch, tmp_path):
    """G10.20：整轮都撞网络抖动时跳过本轮，把预算留给后续轮次。"""
    def always_down(*_a, **_k):
        raise RuntimeError("所有模型不可用 - ConnectTimeout")

    monkeypatch.setattr(dg, "_call_repair_llm", always_down)
    monkeypatch.setattr(dg, "progress",
                        lambda prev, cur: "first" if prev is None else "converging")
    ws = _ws_with_baseline(tmp_path)
    bad = {"op": "create", "path": "tests/test_bad.py",
           "content": "def test_bad():\n    assert False\n"}
    out = dg.gate(_ctx(ws, [bad]), "write_code")
    assert out["rounds"] == dg._MAX_REPAIR_ROUNDS
    assert "LLM 修复异常" in out["reason"]
    assert out["partial_delivery"]


def test_progress_collection_error_type_change_is_converging():
    """G10.22：两轮都无法收集(-1)时，错误类型变化仍是进展，不能判 stalled。"""
    prev = {"sig": "aaa", "failed_count": -1,
            "error_types": ["ImportError", "ModuleNotFoundError"]}
    cur = {"sig": "bbb", "failed_count": -1,
           "error_types": ["ImportError", "NameError"]}
    assert dg.progress(prev, cur) == "converging"
    # 真实签名完全不变 → 仍然止损
    assert dg.progress(prev, prev) == "stalled"


def _router_files():
    return {
        "backend/__init__.py": "",
        "backend/routers/__init__.py": "",
        "backend/routers/orders.py": (
            "from fastapi import APIRouter\n\n"
            "router = APIRouter()\n\n"
            "@router.get('/')\ndef list_orders():\n    return []\n"),
        "backend/main.py": (
            "from fastapi import FastAPI\n\n"
            "app = FastAPI()\n"
            "app.include_router(orders_router, prefix='/orders')\n"),
        "tests/test_root.py": (
            "from backend.main import app\n\n\n"
            "def test_root():\n    assert app is not None\n"),
    }


def test_undefined_router_import_repaired_deterministically():
    """G10.22：main.py 引用未导入的 orders_router → 补 alias import 后 pytest 通过。"""
    files = _router_files()
    ok0, err = dg._run_pytest(files)
    assert not ok0 and "orders_router" in err
    fixed, fixes = dg._repair_undefined_router_imports(
        files, "NameError: name 'orders_router' is not defined")
    assert fixes and "router as orders_router" in fixed["backend/main.py"]
    ok, out = dg._run_pytest(fixed)
    assert ok, out[-600:]


def test_undefined_router_import_skips_ambiguous_providers():
    """有两个 APIRouter 定义者时不猜，交回 LLM 修复轮。"""
    files = _router_files()
    files["backend/routers/inventory.py"] = (
        "from fastapi import APIRouter\n\ninv = APIRouter()\n")
    fixed, fixes = dg._repair_undefined_router_imports(
        files, "NameError: name 'orders_router' is not defined")
    assert fixes == [] and fixed["backend/main.py"] == files["backend/main.py"]


def test_retry_with_deterministic_fix_avoids_llm_round(monkeypatch):
    """确定性分诊成功时不应再消耗 LLM 修复轮次。"""
    files = _router_files()
    fixes = []
    cand, ok, out = dg._retry_with_deterministic_fix(
        files, "NameError: name 'orders_router' is not defined", fixes)
    assert ok and fixes
    assert "router as orders_router" in cand["backend/main.py"]


def test_gate_adaptive_budget_stops_on_stall(tmp_path, monkeypatch):
    """失败签名停滞 → 立即止损，不再多烧 LLM 轮次。"""
    ws = _ws_with_baseline(tmp_path)
    (ws / "backend" / "broken.py").write_text("VALUE = 1\n", encoding="utf-8")
    bad = {"op": "create", "path": "tests/test_bad.py",
           "content": "def test_bad():\n    assert False\n"}
    ctx = _ctx(ws, [bad])
    calls = []

    def fake_llm(*a, **k):
        calls.append(1)
        return "# FILE: tests/test_bad.py"

    monkeypatch.setattr("python_worker.agents.qwen.qwen_api.call_llm", fake_llm)
    monkeypatch.setattr("python_worker.file_ops.parse_fileops_v3",
                        lambda _r: [{"op": "modify", "path": "tests/test_bad.py",
                                     "content": "def test_bad():\n    assert False  # noop\n"}])
    out = dg.gate(ctx, "write_code")
    assert out["partial_delivery"]
    assert len(calls) <= 2, f"停滞时不应继续调用 LLM: {len(calls)}"
    assert any(h["progress"] == "stalled" for h in out["history"])


# ── G10.24：收集期崩溃的根因级签名 ────────────────────────────────

_CRASH_A = (
    "ImportError while loading conftest "
    "'C:\\tmp\\alphapilot-gate-AAA\\tests\\conftest.py'.\n"
    "backend\\services\\order_service.py:8: in <module>\n"
    "E   SyntaxError: unexpected indent\n")
_CRASH_B = (
    "ImportError while loading conftest "
    "'C:\\tmp\\alphapilot-gate-BBB\\tests\\conftest.py'.\n"
    "backend\\services\\inventory_service.py:7: in <module>\n"
    "E   SyntaxError: unexpected indent\n")


def test_crash_fingerprint_separates_different_root_causes():
    """v5_1 的 R6/R8：错误类型集合相同但坏文件换了，不能算同一签名。"""
    a, b = dg.failure_signature(_CRASH_A), dg.failure_signature(_CRASH_B)
    assert a["failed_count"] == b["failed_count"] == -1
    assert set(a["error_types"]) == set(b["error_types"])
    assert a["crash"] and b["crash"] and a["crash"] != b["crash"]
    assert a["sig"] != b["sig"]
    assert dg.progress(a, b) == "converging"


def test_crash_fingerprint_normalizes_tmpdir_and_lineno():
    """临时目录名与行号是噪声，换掉不应制造假进展。"""
    moved = _CRASH_A.replace("AAA", "ZZZ").replace(
        "order_service.py:8", "order_service.py:12")
    assert dg._crash_fingerprint(moved) == dg._crash_fingerprint(_CRASH_A)


def test_same_root_cause_is_still_stalled():
    """净加严证据：根因没变时依旧立即止损，没有多烧 LLM 轮次。"""
    a = dg.failure_signature(_CRASH_A)
    assert dg.progress(a, dg.failure_signature(_CRASH_A)) == "stalled"


def test_failure_signature_backwards_compatible_without_crash_info():
    """可量化失败（有 `N failed`）时签名公式与 G10.15 完全一致。"""
    out = "FAILED tests/test_a.py::test_one - KeyError: 'id'\n1 failed in 0.3s"
    sig = dg.failure_signature(out)
    import hashlib
    expected = hashlib.sha256(
        ("tests/test_a.py::test_one#KeyError").encode("utf-8")
    ).hexdigest()[:12]
    assert sig["sig"] == expected
    assert sig["crash"] == ""


# ── G10.24：断裂多行 import 的确定性修复 ──────────────────────────

_BROKEN_IMPORT = """from sqlalchemy.orm import Session
from backend.schemas.order import OrderCreate
    OrderNotFoundException,
    InvalidStatusTransitionException,
    InvalidStatusValueException
)


class OrderService:
    pass
"""


def test_broken_multiline_import_is_repaired_deterministically():
    """v5_1 的 R10 真实产物形态：零 LLM 修复成合法单行 import。"""
    import ast
    files = {"backend/services/order_service.py": _BROKEN_IMPORT,
             "tests/test_a.py": "def test_a(): pass\n"}
    with pytest.raises(SyntaxError):
        ast.parse(_BROKEN_IMPORT)
    out, fixes = dg._repair_broken_syntax(files)
    assert len(fixes) == 1 and "断裂的多行 import" in fixes[0]
    ast.parse(out["backend/services/order_service.py"])
    assert out["tests/test_a.py"] == files["tests/test_a.py"]
    assert ")" not in out["backend/services/order_service.py"].splitlines()[2]


def test_broken_syntax_repair_fails_closed_on_unknown_shape():
    """认不出的语法坏形态绝不臆造删除，完整交回 LLM 修复轮。"""
    bad = "def f(:\n    pass\n"
    out, fixes = dg._repair_broken_syntax({"x.py": bad})
    assert fixes == [] and out["x.py"] == bad
    valid = "def f():\n    return 1\n"
    assert dg._repair_broken_syntax({"x.py": valid})[1] == []


def test_retry_with_deterministic_fix_repairs_syntax_without_llm(monkeypatch):
    """语法坏候选先走确定性修复再复验，不需要任何一次 LLM 调用。"""
    import ast
    seen = {}

    def fake_run(files):
        seen.update(files)
        for path, src in files.items():
            if path.endswith(".py"):
                ast.parse(src)
        return True, "候选工作区 pytest 通过"

    monkeypatch.setattr(dg, "_run_pytest", fake_run)
    files = {
        "backend/schemas/order.py": (
            "OrderCreate = 1\nOrderNotFoundException = 2\n"
            "InvalidStatusTransitionException = 3\n"
            "InvalidStatusValueException = 4\n"),
        "backend/services/order_service.py": _BROKEN_IMPORT,
    }
    fixes = []
    cand, ok, _out = dg._retry_with_deterministic_fix(
        files, "E   SyntaxError: unexpected indent", fixes)
    assert ok is True
    assert any("断裂的多行 import" in f for f in fixes)
    ast.parse(seen["backend/services/order_service.py"])


# ── G10.25：LLM 调用硬超时与闸门总预算 ────────────────────────────

def test_hard_timeout_returns_promptly_on_hung_llm():
    """v6_1 实证：上游半开连接不抛异常，必须在硬上限内返回而非无限挂起。"""
    import threading
    import time as _time
    release = threading.Event()

    def hanging(*_a, **_k):
        release.wait(1.0)
        return "late"

    started = _time.monotonic()
    try:
        with pytest.raises(TimeoutError) as exc:
            dg._call_llm_hard_timeout(hanging, "p", 0.1, 0.2)
        assert dg._is_transient_llm_error(exc.value) is True
        assert (_time.monotonic() - started) < 0.9, "shutdown 不应等待挂起线程"
    finally:
        release.set()


def test_repair_llm_retries_on_hung_call(monkeypatch):
    """真挂起被硬超时转成瞬断异常，走 G10.20 退避重试并能在下一次恢复。"""
    monkeypatch.setattr(dg.time, "sleep", lambda _s: None)
    calls = []

    def flaky(*_a, **_k):
        calls.append(1)
        if len(calls) == 1:
            import threading
            threading.Event().wait(0.4)  # 第一次真挂起，超过 0.1s 硬上限
        return "recovered"

    result = dg._call_repair_llm("p", 0.1, flaky, timeout=0.1)
    assert result == "recovered"
    assert len(calls) == 2
    assert dg._REPAIR_LLM_ATTEMPTS == 3


def test_gate_total_budget_stops_zombie(monkeypatch, tmp_path):
    """总预算耗尽必须立即收尾并写回结果，绝不留下无结果的任务。"""
    llm_calls = []
    monkeypatch.setattr(dg, "_GATE_TOTAL_BUDGET_SEC", 0)
    monkeypatch.setattr("python_worker.agents.qwen.qwen_api.call_llm",
                        lambda *a, **k: llm_calls.append(1) or "")
    ws = _ws_with_baseline(tmp_path)
    bad = {"op": "create", "path": "tests/test_bad.py",
           "content": "def test_bad():\n    assert False\n"}
    out = dg.gate(_ctx(ws, [bad]), "write_code")
    assert "总预算" in out["reason"]
    assert out["partial_delivery"] and not out["passed"]
    assert llm_calls == [], "预算耗尽后不应再发起 LLM 调用"


def test_hard_timeout_does_not_break_normal_llm():
    """正常快速返回时硬超时包装完全透明。"""
    assert dg._call_llm_hard_timeout(
        lambda p, t: f"ok:{t}", "p", 0.3, 5) == "ok:0.3"
