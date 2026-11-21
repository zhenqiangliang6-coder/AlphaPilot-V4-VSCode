# python_worker/tests/test_g1034_contracts.py
"""G10.34 新增测试状态码期望对齐 + 自洽完整交付清单。

shopflow_v13_1 的 R8 实证：LLM 生成的 tests/test_inventory.py 里有两处
`assert response.status_code == 201`，而既有 POST /orders 与题面写死的库存
POST 都是 200。闸门 10 → 7 → 2 failed 后签名不变判 stalled，分层收敛因
「只留新增文件」造出 404 孤儿态，进而全量回滚，把题面要求的三个新增文件
一并抹掉：R8 质量门三文件全 False，R10 因 inventory.py 缺失 FAIL-CLOSED。
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker import delivery_gate as dg  # noqa: E402


ROUTER_200 = (
    "from fastapi import APIRouter\n"
    "router = APIRouter()\n"
    "@router.post(\"/\")\n"
    "def create_order(payload: dict):\n"
    "    return {\"status\": \"ok\"}\n"
)
NEW_TEST = (
    "def test_order_deducts_inventory():\n"
    "    response = client.post(\"/orders/\", json={})\n"
    "    assert response.status_code == 201\n"
    "    assert response.status_code == 201\n"
)
BASE = {
    "tests/test_ok.py": "def test_ok():\n    assert True\n",
    "backend/routers/orders.py": ROUTER_200,
}


def _files():
    return dict(BASE, **{"tests/test_inventory.py": NEW_TEST})


def test_post_status_codes_defaults_to_200():
    """无显式 status_code 的 POST 按 FastAPI 默认判 200。"""
    assert dg._post_status_codes(dict(BASE)) == [200]


def test_post_status_codes_explicit_and_fail_closed():
    """显式数值 / HTTP_ 常量可解析；无法判定语义的常量 → 空列表放弃修复。"""
    explicit = dict(BASE)
    explicit["backend/routers/orders.py"] = (
        "@router.post(\"/\", status_code=201)\ndef f(): pass\n")
    assert dg._post_status_codes(explicit) == [201]
    symbolic = dict(BASE)
    symbolic["backend/routers/orders.py"] = (
        "@router.post(\"/\", status_code=status.HTTP_200_OK)\n"
        "def f(): pass\n")
    assert dg._post_status_codes(symbolic) == [200]
    unknown = dict(BASE)
    unknown["backend/routers/orders.py"] = (
        "@router.post(\"/\", status_code=SOME_CUSTOM_CONST)\n"
        "def f(): pass\n")
    assert dg._post_status_codes(unknown) == []


def test_new_test_201_is_aligned_to_real_router_status():
    """新增测试的两处 201 期望改为真实 200，入参不变且幂等。"""
    files = _files()
    out, fixes = dg._repair_new_test_status_expectation(files, "", set(BASE))
    assert len(fixes) == 1
    assert "== 200" in out["tests/test_inventory.py"]
    assert "== 201" not in out["tests/test_inventory.py"]
    assert files["tests/test_inventory.py"] == NEW_TEST, "不得修改入参"
    again, fixes2 = dg._repair_new_test_status_expectation(
        out, "", set(BASE))
    assert again == out and fixes2 == [], "修复必须幂等"


def test_existing_tests_and_explicit_201_are_untouched():
    """既有测试不受影响；router 真为 201 时绝不反向改测试。"""
    files = dict(BASE)
    files["tests/test_ok.py"] = (
        "def test_ok():\n    assert response.status_code == 201\n")
    out, fixes = dg._repair_new_test_status_expectation(
        files, "", set(BASE))
    assert fixes == []
    assert out == files

    router201 = dict(BASE)
    router201["backend/routers/orders.py"] = (
        "@router.post(\"/\", status_code=201)\ndef f(): pass\n")
    router201["tests/test_inventory.py"] = NEW_TEST
    out2, fixes2 = dg._repair_new_test_status_expectation(
        router201, "", set(BASE))
    assert fixes2 == [] and out2 == router201


def test_syntax_guard_skips_broken_new_test():
    """语法不合法的新增测试不写入候选。"""
    files = dict(BASE)
    files["tests/test_inventory.py"] = (
        "def broken(:\n    assert response.status_code == 201\n")
    out, fixes = dg._repair_new_test_status_expectation(
        files, "", set(BASE))
    assert fixes == []
    assert out["tests/test_inventory.py"] == files["tests/test_inventory.py"]


def test_gate_delivers_fixed_new_test_content(monkeypatch):
    """闸门入口修复后候选 pytest 绿，交付清单里不含 201 期望。"""
    ctx = {
        "meta": {"workspace_path": "C:/tmp/ws",
                 "user_request": "增加库存模块，POST / 返回 200"},
        "final_file_ops": [
            {"op": "create", "path": "tests/test_inventory.py",
             "content": NEW_TEST},
            {"op": "create", "path": "backend/models/inventory.py",
             "content": "class Inventory: pass\n"},
        ],
    }
    monkeypatch.setattr(dg, "snapshot_workspace", lambda ws: dict(BASE))
    monkeypatch.setattr(dg, "_MAX_REPAIR_ROUNDS", 0)
    monkeypatch.setattr(dg, "_retry_with_deterministic_fix",
                        lambda cand, out, fixes: (cand, False, out))

    def fake_pytest(files):
        if "== 201" in files.get("tests/test_inventory.py", ""):
            return False, "FAILED tests/test_inventory.py - AssertionError\n1 failed"
        return True, ""

    monkeypatch.setattr(dg, "_run_pytest", fake_pytest)
    result = dg.gate(ctx, "incremental_feature")
    assert result["passed"] is True
    delivered = {str(o.get("path")): o.get("content")
                 for o in ctx["final_file_ops"] if o.get("content")}
    assert "tests/test_inventory.py" in delivered
    assert "== 200" in delivered["tests/test_inventory.py"]
    assert any("201 → 200" in f for f in result["fixes"])


BAD_OUTPUT = "FAILED tests/test_new.py - AssertionError\n1 failed"
WORSE_OUTPUT = ("FAILED tests/test_new.py - AssertionError\n"
                "FAILED tests/test_ok.py - AssertionError\n2 failed")


def test_selfcontained_full_ops_are_not_rolled_back(monkeypatch):
    """完整交付清单真实 pytest 通过时不按「既有文件」身份全量回滚。"""
    ops = [
        {"op": "create", "path": "tests/test_new.py",
         "content": "def test_new(): assert True\n"},
        {"op": "modify", "path": "backend/routers/orders.py",
         "content": ROUTER_200 + "register_inventory()\n"},
    ]
    ctx = {
        "meta": {"workspace_path": "C:/tmp/ws",
                 "user_request": "给订单模块补一点日志，保持现有行为。"},
        "final_file_ops": [dict(o) for o in ops],
    }
    monkeypatch.setattr(dg, "snapshot_workspace", lambda ws: dict(BASE))
    monkeypatch.setattr(dg, "_MAX_REPAIR_ROUNDS", 0)
    monkeypatch.setattr(dg, "_retry_with_deterministic_fix",
                        lambda cand, out, fixes: (cand, False, out))
    calls = {"n": 0}

    def fake_pytest(files):
        calls["n"] += 1
        if calls["n"] == 1:
            return False, BAD_OUTPUT          # 入口候选：红
        if calls["n"] == 2:
            return True, ""                   # base：绿
        if calls["n"] == 3:
            return True, ""                   # full：绿（入口联动齐全）
        return False, WORSE_OUTPUT            # kept：孤儿态更差

    monkeypatch.setattr(dg, "_run_pytest", fake_pytest)
    result = dg.gate(ctx, "incremental_feature")
    assert result["full_selfcontained_delivery"] is True
    assert result.get("full_rollback") is not True
    assert any("register_inventory" in str(o.get("content"))
               for o in ctx["final_file_ops"]), "既有入口联动必须保留"
    assert "完整交付清单" in result["reason"]
