# python_worker/tests/test_explicit_status_contract.py
"""G10.29 题面显式状态码约束的确定性修复契约。

v8 第 1 遍 R10 的真实失败：题面已写死「POST / 返回 200（不是 201）」，
LLM 重构服务层仍生成 `status_code=status.HTTP_201_CREATED`，pytest 全绿
但语义契约门判 `inventory: POST / 状态码 201 != 期望 200`，整轮质量失败。
本文件锁死：题面明令禁止的状态码在候选工作区落盘前被定点纠正，
且纠正范围严格限定在路由装饰器的 status_code= 上。
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker import delivery_gate as dg  # noqa: E402


def test_repairs_literal_and_constant_status_codes():
    files = {
        "backend/routers/inventory.py": (
            "@router.post('/', status_code=status.HTTP_201_CREATED)\n"
            "def create(): ...\n"
            "@router.put('/{name}', status_code=201)\n"
            "def update(): ...\n"
        )
    }
    out, fixes = dg._repair_explicit_status_code(
        files, "重构服务层；POST / 返回 200（不是 201）")
    assert "HTTP_201_CREATED" not in out["backend/routers/inventory.py"]
    assert "status_code=201" not in out["backend/routers/inventory.py"]
    assert out["backend/routers/inventory.py"].count("status_code=200") == 2
    assert fixes == ["backend/routers/inventory.py: status_code 201 → 200"]
    assert "201" in files["backend/routers/inventory.py"], "原始 files 不得被就地修改"


def test_halfwidth_parentheses_also_match():
    out, fixes = dg._repair_explicit_status_code(
        {"backend/routers/orders.py": "x = dict(status_code=201)\n"},
        "POST / 返回 200 (不是 201)")
    assert out["backend/routers/orders.py"] == "x = dict(status_code=200)\n"
    assert fixes


def test_no_explicit_constraint_leaves_code_unchanged():
    src = "@router.post('/', status_code=status.HTTP_201_CREATED)\n"
    files = {"backend/routers/inventory.py": src}
    out, fixes = dg._repair_explicit_status_code(files, "把路由逻辑提取到服务层")
    assert out == files
    assert fixes == []


def test_other_status_codes_and_non_router_files_untouched():
    files = {
        "backend/routers/orders.py": (
            "@router.delete('/{oid}', status_code=status.HTTP_204_NO_CONTENT)\n"
            "def delete(): ...\n"
        ),
        "backend/services/order_service.py": "CREATED = 201\n",
        "tests/test_orders.py": "assert resp.status_code == 201\n",
    }
    out, fixes = dg._repair_explicit_status_code(
        files, "POST / 返回 200（不是 201）")
    assert out == files
    assert fixes == []


def test_business_literals_not_rewritten():
    files = {
        "backend/routers/inventory.py": (
            "@router.post('/', status_code=status.HTTP_201_CREATED)\n"
            "def create():\n"
            "    if qty == 201:\n"
            "        return {'legacy_code': 201}\n"
        )
    }
    out, _ = dg._repair_explicit_status_code(
        files, "POST / 返回 200（不是 201）")
    body = out["backend/routers/inventory.py"]
    assert "if qty == 201" in body
    assert "'legacy_code': 201" in body
    assert "status_code=200" in body


def test_gate_feeds_contract_fix_into_candidate(monkeypatch):
    """闸门主链路：修复发生在真实 pytest 之前，并进入 fixes 证据。"""
    monkeypatch.setattr(dg, "snapshot_workspace",
                        lambda ws: {"tests/test_dummy.py": "def test_ok(): pass\n"})
    seen = {}

    def fake_pytest(files):
        seen["candidate"] = dict(files)
        return True, ""

    monkeypatch.setattr(dg, "_run_pytest", fake_pytest)
    monkeypatch.setattr(dg, "_finalize_verified_pass", lambda *a, **k: True)

    ctx = {
        "meta": {
            "workspace_path": "C:/tmp/ws",
            "user_request": "POST / 返回 200（不是 201）",
        },
        "final_file_ops": [{
            "op": "update",
            "path": "backend/routers/inventory.py",
            "content": "@router.post('/', status_code=status.HTTP_201_CREATED)\n"
                       "def create(): ...\n",
        }],
    }
    result = dg.gate(ctx, "refactor")
    assert result["ran"] is True
    assert any("status_code 201 → 200" in f for f in result["fixes"])
    assert "status_code=200" in seen["candidate"]["backend/routers/inventory.py"]
