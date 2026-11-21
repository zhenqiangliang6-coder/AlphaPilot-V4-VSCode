# python_worker/tests/test_g1032_contracts.py
"""G10.32 三项确定性契约：自愈进展判定 / 端点级白名单 / 结构契约对齐。

v11 第 1 遍 R8→R10 的连锁失败链：
1. 闸门轮末把「修复后签名」错存为 prev_sig，轮首再对同一输出取签名，
   必然判 stalled；5 轮自愈预算只用了 2 轮，progress() 里
   「收集崩溃 → 可收集」的 converging 分支永远不可达。
2. 题面「修改 POST /orders 逻辑」正向点名了要改的既有文件，白名单却
   只认 .py 路径，增量契约保护把 backend/routers/orders.py 的写操作
   整个丢弃，库存扣减逻辑根本进不了候选工作区。
3. 磁盘上 ORM 类叫 InventoryItem / 表 inventory_items，R10 语义契约
   FAIL-CLOSED 要求提取到 Inventory，生成 PROMPT 前就抛异常。

本文件锁死三处修复，且验证「不放宽题面、不放宽验收、不改入参、幂等」。
"""

import ast
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker import delivery_gate as dg  # noqa: E402
from python_worker.tests import test_observe_task_system as obs  # noqa: E402

try:
    from python_worker.agents.qwen import step_runner as sr  # noqa: E402
except Exception:  # pragma: no cover - 重依赖缺失时跳过白名单测试
    sr = None

CRASH_OUT = (
    "ImportError while loading conftest 'tests/conftest.py'.\n"
    "E   NameError: name 'Inventory' is not defined\n"
    "ERROR tests/test_inventory.py\n"
)
SIX_FAILED_OUT = (
    "FAILED tests/test_inventory.py::test_a - AttributeError\n"
    "FAILED tests/test_inventory.py::test_b - AttributeError\n"
    "FAILED tests/test_inventory.py::test_c - AttributeError\n"
    "FAILED tests/test_inventory.py::test_d - AttributeError\n"
    "FAILED tests/test_inventory.py::test_e - AttributeError\n"
    "FAILED tests/test_inventory.py::test_f - AttributeError\n"
    "6 failed in 1.2s\n"
)


# ── 1. 自愈进展判定：轮首比较「上一轮修复前 vs 修复后」 ──────────────

def test_progress_directly_recognizes_crash_to_collectable():
    prev = dg.failure_signature(CRASH_OUT)
    cur = dg.failure_signature(SIX_FAILED_OUT)
    assert prev["failed_count"] < 0
    assert dg.progress(prev, cur) == "converging"


def test_gate_uses_round_start_signature_and_spends_budget(monkeypatch):
    calls = {"n": 0}

    def fake_pytest(files):
        calls["n"] += 1
        if calls["n"] == 1:
            return False, CRASH_OUT
        return False, SIX_FAILED_OUT

    monkeypatch.setattr(dg, "_run_pytest", fake_pytest)
    repairs = {"n": 0}

    def fake_repair(*a, **kw):
        repairs["n"] += 1
        return f"PATCH #{repairs['n']}"

    monkeypatch.setattr(dg, "_call_repair_llm", fake_repair)
    from python_worker import file_ops
    monkeypatch.setattr(
        file_ops, "parse_fileops_v3",
        lambda reply: [{"op": "modify", "path": "tests/test_inventory.py",
                        "content": f"def test_a(): assert True  # {reply}\n"}])
    monkeypatch.setattr(dg, "_GATE_TOTAL_BUDGET_SEC", 300)

    ctx = {
        "meta": {"workspace_path": "C:/fake_ws",
                 "user_request": "给系统增加库存模块"},
        "final_file_ops": [
            {"op": "modify", "path": "tests/test_inventory.py",
             "content": "def test_a(): assert False\n"}],
    }
    monkeypatch.setattr(dg, "snapshot_workspace", lambda ws: {
        "tests/test_ok.py": "def test_ok(): assert True\n"})
    result = dg.gate(ctx, "incremental_feature")

    history = result["history"]
    assert len(history) >= 2, history
    assert history[0]["progress"] == "first"
    # 旧实现在这里是 stalled（cur.sig == new_sig1），预算直接止损
    assert history[1]["progress"] == "converging", history
    assert result["rounds"] >= 3, history


# ── 2. 题面端点级点名放行既有 router 文件 ────────────────────────────

def test_endpoint_edit_target_whitelists_orders_router():
    if sr is None:
        return
    targets = sr._explicitly_named_edit_targets(obs.PROMPT_ROUND_8)
    assert "backend/main.py" in targets
    assert "backend/routers/orders.py" in targets, sorted(targets)
    assert "tests/test_orders.py" not in targets
    assert "tests/conftest.py" not in targets


def test_endpoint_edit_target_does_not_leak_to_protected_rounds():
    if sr is None:
        return
    targets = sr._explicitly_named_edit_targets(obs.PROMPT_ROUND_9)
    assert "backend/main.py" not in targets, sorted(targets)
    assert not any(p.startswith("backend/routers/") for p in targets), sorted(targets)


# ── 3. 题面显式结构契约对齐 ──────────────────────────────────────────

MODEL_SRC = (
    "from backend.database import Base\n"
    "from sqlalchemy import Column, String, Integer, Float\n"
    "class InventoryItem(Base):\n"
    '    __tablename__ = "inventory_items"\n'
    "    product_name = Column(String, unique=True)\n"
    "    quantity = Column(Integer)\n"
)
ROUTER_SRC = (
    "from fastapi import APIRouter\n"
    'router = APIRouter(prefix="/inventory")\n'
    "from backend.models.inventory import InventoryItem\n"
    "@router.post('/')\n"
    "def create(item: dict):\n"
    "    return InventoryItem(**item)\n"
)
MAIN_SRC = (
    "from fastapi import FastAPI\n"
    "from backend.routers import orders, inventory\n"
    "app = FastAPI()\n"
    "app.include_router(orders.router)\n"
    "app.include_router(inventory.router)\n"
)


def _candidate():
    return {
        "tests/test_ok.py": "def test_ok(): assert True\n",
        "backend/models/inventory.py": MODEL_SRC,
        "backend/routers/inventory.py": ROUTER_SRC,
        "backend/main.py": MAIN_SRC,
    }


def test_structure_contract_parsed_from_round8():
    info = dg._explicit_structure_contract(obs.PROMPT_ROUND_8)
    assert info is not None
    assert info["cls"] == "Inventory"
    assert info["table"] == "inventory"
    assert info["model_file"] == "backend/models/inventory.py"
    assert info["mount_var"] == "inventory_router"
    assert info["prefix"] == "/inventory"
    assert info["router_file"] == "backend/routers/inventory.py"


def test_alignment_fixes_class_table_mount_and_prefix():
    before = _candidate()
    after, fixes = dg._repair_explicit_structure_contract(
        before, obs.PROMPT_ROUND_8)
    assert "InventoryItem" not in after["backend/models/inventory.py"]
    assert "class Inventory(Base)" in after["backend/models/inventory.py"]
    assert '__tablename__ = "inventory"' in after["backend/models/inventory.py"]
    assert "InventoryItem" not in after["backend/routers/inventory.py"]
    assert 'APIRouter(prefix=' not in after["backend/routers/inventory.py"]
    main = after["backend/main.py"]
    assert 'app.include_router(inventory_router, prefix="/inventory")' in main
    assert "app.include_router(inventory.router)" not in main
    assert "from backend.routers.inventory import router as inventory_router" in main
    assert "app.include_router(orders.router)" in main
    for p, s in after.items():
        if p.endswith(".py"):
            ast.parse(s)
    assert fixes
    # 入参不可变
    assert before["backend/models/inventory.py"] == MODEL_SRC


def test_alignment_is_idempotent():
    once, _ = dg._repair_explicit_structure_contract(
        _candidate(), obs.PROMPT_ROUND_8)
    twice, fixes2 = dg._repair_explicit_structure_contract(
        once, obs.PROMPT_ROUND_8)
    assert twice == once
    assert fixes2 == []


def test_alignment_skips_when_target_class_already_exists():
    files = _candidate()
    files["backend/models/inventory.py"] = files[
        "backend/models/inventory.py"].replace("InventoryItem", "Inventory")
    files["backend/routers/inventory.py"] = files[
        "backend/routers/inventory.py"].replace("InventoryItem", "Inventory")
    after, _ = dg._repair_explicit_structure_contract(files, obs.PROMPT_ROUND_8)
    assert "class Inventory(Base)" in after["backend/models/inventory.py"]
    assert "InventoryItem" not in after["backend/models/inventory.py"]


def test_alignment_noop_for_unrelated_request():
    before = _candidate()
    after, fixes = dg._repair_explicit_structure_contract(
        before, obs.PROMPT_ROUND_9)
    assert after == before
    assert fixes == []


def test_alignment_respects_syntax_guard():
    files = _candidate()
    files["backend/routers/inventory.py"] = ROUTER_SRC + "\nthis is ( broken\n"
    after, _ = dg._repair_explicit_structure_contract(files, obs.PROMPT_ROUND_8)
    # 无法安全改写的文件保持原样，不把坏语法扩散进候选
    assert after["backend/routers/inventory.py"] == files[
        "backend/routers/inventory.py"]
