# python_worker/tests/test_incremental_contract.py
"""增量功能「不要破坏现有功能」契约保护回归契约（G10.14）。

真实故障（shopflow_full_run1b）：R8 题面明写「不要破坏现有功能」，
模型却把既有 backend/schemas/order.py、backend/routers/orders.py 等
全量重写，删掉 OrderResponse.id、改掉 HTTP 方法，pytest 15 failed
（422 / 405 / KeyError: 'id'）；ShadowVerify 两轮自检失败仍放行交付，
R9/R10 前置连锁崩。
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker.agents.qwen.step_runner import (  # noqa: E402
    _enforce_incremental_contract,
    _explicitly_named_edit_targets,
    _public_contract,
)

R8_REQ = "给 ShopFlow 增加「库存管理」模块。仔细阅读已有代码后再动手，不要破坏现有功能。"
NEUTRAL_REQ = "给 ShopFlow 增加「库存管理」模块，按需求实现即可。"

# G10.16 实证题面片段（逐字取自 test_observe_task_system.py 的 R8/R9/R10）
R8_MAIN_LINE = (
    "- backend/main.py 必须用 `include_router(inventory_router, "
    'prefix="/inventory")` 注册库存路由，'
)
R9_MAIN_LINE = "注意：不要改动 backend/main.py，也不要新增/删除任何 API 端点或改动状态码。"
R10_MAIN_LINE = (
    "6. backend/main.py 属于受保护文件：read_root() 必须原样返回 "
    '{{"message": "ShopFlow API is running"}}，其余内容禁止修改。'
)

OLD_SCHEMA = '''from pydantic import BaseModel


class OrderResponse(BaseModel):
    id: str
    product_name: str
    quantity: int
'''

OLD_ROUTER = '''from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_orders(limit: int = 10):
    return []


@router.post("/")
def create_order(payload: dict):
    return payload
'''


def _ctx(tmp_path, path, old, new, req=R8_REQ, intent="write_code"):
    f = tmp_path / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(old, encoding="utf-8")
    return {
        "meta": {"user_request": req, "workspace_path": str(tmp_path)},
        "final_file_ops": [{"op": "modify", "path": path, "content": new}],
    }


def test_public_contract_extraction():
    c = _public_contract(OLD_ROUTER)
    assert ("route", "get", "/") in c
    assert ("route", "post", "/") in c
    assert ("func", "list_orders", ("limit",)) in c
    assert ("field", "OrderResponse", "id") in _public_contract(OLD_SCHEMA)


def test_field_removal_is_blocked(tmp_path):
    """删掉响应字段 id（R8 的 KeyError: 'id' 根因）→ 保留磁盘现状。"""
    new = OLD_SCHEMA.replace("    id: str\n", "")
    ctx = _ctx(tmp_path, "backend/schemas/order.py", OLD_SCHEMA, new)
    out = _enforce_incremental_contract(ctx, "write_code")
    assert out["applied"] and out["blocked"] == ["backend/schemas/order.py"]
    assert ctx["final_file_ops"] == []
    assert "id" in out["reasons"]["backend/schemas/order.py"]


def test_route_and_signature_removal_is_blocked(tmp_path):
    """删路由 / 改函数签名（R8 的 405 / 422 根因）→ 保留磁盘现状。"""
    new = OLD_ROUTER.replace('@router.get("/")\ndef list_orders(limit: int = 10):',
                             '@router.get("/")\ndef list_orders():')
    ctx = _ctx(tmp_path, "backend/routers/orders.py", OLD_ROUTER, new)
    out = _enforce_incremental_contract(ctx, "write_code")
    assert out["blocked"] == ["backend/routers/orders.py"]


def test_syntax_error_is_blocked(tmp_path):
    new = OLD_SCHEMA.replace("from pydantic import BaseModel",
                             "from pydantic import   # broken")
    ctx = _ctx(tmp_path, "backend/schemas/order.py", OLD_SCHEMA, new)
    out = _enforce_incremental_contract(ctx, "write_code")
    assert out["blocked"] == ["backend/schemas/order.py"]
    assert "语法错误" in out["reasons"]["backend/schemas/order.py"]


def test_additive_change_passes(tmp_path):
    """加法式增量（新增字段/新函数/新路由）不受影响。"""
    new = OLD_SCHEMA + "\n\nclass InventoryResponse(BaseModel):\n    sku: str\n"
    ctx = _ctx(tmp_path, "backend/schemas/order.py", OLD_SCHEMA, new)
    out = _enforce_incremental_contract(ctx, "write_code")
    assert not out["applied"] and not out["blocked"]
    assert ctx["final_file_ops"][0]["content"] == new


def test_new_files_are_not_restricted(tmp_path):
    """新增文件（磁盘不存在）一律放行。"""
    ctx = _ctx(tmp_path, "backend/models/inventory.py", OLD_SCHEMA, OLD_SCHEMA)
    (tmp_path / "backend/models/inventory.py").unlink()
    ctx["final_file_ops"][0]["path"] = "backend/models/inventory.py"
    out = _enforce_incremental_contract(ctx, "write_code")
    assert not out["blocked"] and ctx["final_file_ops"]


def test_fail_open_without_guard_marker(tmp_path):
    """没有「不要破坏现有功能」措辞（R6/R9/R10）→ 完全不生效。"""
    new = OLD_SCHEMA.replace("    id: str\n", "")
    ctx = _ctx(tmp_path, "backend/schemas/order.py", OLD_SCHEMA, new, req=NEUTRAL_REQ)
    out = _enforce_incremental_contract(ctx, "write_code")
    assert not out["applied"] and not out["blocked"]
    assert ctx["final_file_ops"][0]["content"] == new


def test_fail_open_for_other_intents(tmp_path):
    new = OLD_SCHEMA.replace("    id: str\n", "")
    ctx = _ctx(tmp_path, "backend/schemas/order.py", OLD_SCHEMA, new)
    out = _enforce_incremental_contract(ctx, "fix_code")
    assert not out["applied"] and not out["blocked"]


def test_internal_ops_and_init_are_always_kept(tmp_path):
    ctx = _ctx(tmp_path, "backend/__init__.py", OLD_SCHEMA, "x = 1")
    ctx["final_file_ops"].append({"op": "create", "path": "meta", "_internal": True,
                                  "content": "{}"})
    out = _enforce_incremental_contract(ctx, "write_code")
    assert not out["blocked"]
    assert len(ctx["final_file_ops"]) == 2


# ── G10.16: 题面正向点名要修改的既有文件白名单 ──────────────────────

def test_explicit_targets_parses_positive_lines_only():
    """R8 正向点名 main.py / __init__.py；R9、R10 的否定语境严格排除。"""
    assert "backend/main.py" in _explicitly_named_edit_targets(R8_MAIN_LINE)
    assert "backend/models/__init__.py" in _explicitly_named_edit_targets(
        "必须在 backend/models/__init__.py 追加 `from backend.models.inventory import Inventory`，")
    assert _explicitly_named_edit_targets(R9_MAIN_LINE) == set()
    assert _explicitly_named_edit_targets(R10_MAIN_LINE) == set()
    assert _explicitly_named_edit_targets(
        "不要修改 tests/test_orders.py 中已有的测试逻辑，也不要改动 tests/conftest.py") == set()
    # 同一行内出现「必须保证现有测试原样通过」→ 歧义行不认
    assert _explicitly_named_edit_targets(
        "4. 下单时库存扣减——修改 POST /orders 逻辑（必须保证现有 "
        "tests/test_orders.py 原样通过）") == set()


def test_r8_explicitly_named_main_py_is_not_rolled_back(tmp_path):
    """run1e 根因：R8 明确要求改 main.py 注册库存路由，契约保护不得回滚。"""
    req = R8_REQ + "\n" + R8_MAIN_LINE
    new = OLD_SCHEMA.replace("    id: str\n", "")  # 故意制造契约缩水
    ctx = _ctx(tmp_path, "backend/main.py", OLD_SCHEMA, new, req=req)
    out = _enforce_incremental_contract(ctx, "write_code")
    assert not out["applied"] and not out["blocked"]
    assert out["explicit_targets"] == ["backend/main.py"]
    assert out["whitelisted"] == ["backend/main.py"]
    assert ctx["final_file_ops"][0]["content"] == new


def test_negative_context_still_protects_main_py(tmp_path):
    """R9 / R10 的「不要改动 / 受保护」语境下 main.py 仍走契约保护。"""
    for line in (R9_MAIN_LINE, R10_MAIN_LINE):
        req = R8_REQ + "\n" + line  # 保留保护措辞，确保守卫生效
        new = OLD_SCHEMA.replace("    id: str\n", "")
        ctx = _ctx(tmp_path, "backend/main.py", OLD_SCHEMA, new, req=req)
        out = _enforce_incremental_contract(ctx, "write_code")
        assert out["blocked"] == ["backend/main.py"], line
        assert out["whitelisted"] == [], line
        assert ctx["final_file_ops"] == [], line


def test_whitelisted_file_still_needs_valid_syntax(tmp_path):
    """白名单只豁免契约缩水检查，语法坏内容照样拦。"""
    req = R8_REQ + "\n" + R8_MAIN_LINE
    new = OLD_SCHEMA.replace("from pydantic import BaseModel",
                             "from pydantic import   # broken")
    ctx = _ctx(tmp_path, "backend/main.py", OLD_SCHEMA, new, req=req)
    out = _enforce_incremental_contract(ctx, "write_code")
    assert out["blocked"] == ["backend/main.py"]
    assert "语法错误" in out["reasons"]["backend/main.py"]


def test_whitelist_does_not_leak_to_other_files(tmp_path):
    """白名单是文件级的：点名 main.py 不会顺带放过 schemas/order.py。"""
    req = R8_REQ + "\n" + R8_MAIN_LINE
    new = OLD_SCHEMA.replace("    id: str\n", "")
    ctx = _ctx(tmp_path, "backend/schemas/order.py", OLD_SCHEMA, new, req=req)
    out = _enforce_incremental_contract(ctx, "write_code")
    assert out["blocked"] == ["backend/schemas/order.py"]
    assert out["whitelisted"] == []
