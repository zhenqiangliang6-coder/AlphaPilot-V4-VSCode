# -*- coding: utf-8 -*-
"""Round 7 Shadow Mode integration"""

import os, sys, tempfile, importlib.util

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_path = os.path.join(os.path.dirname(__file__), "..", "agents", "qwen", "step_executor", "verification_governor.py")
_spec = importlib.util.spec_from_file_location("verification_governor", _path)
_vg_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vg_mod)
VerificationGovernor = _vg_mod.VerificationGovernor


def _mk_ctx(fp_ops, ws=None):
    if ws is None:
        ws = tempfile.mkdtemp(prefix="r7_")
    return {"workspace_path": ws, "meta": {"skill_id": "x", "task_id": "y"}, "final_file_ops": fp_ops}


def _mk_op(action, path, content, old_content=None):
    return {"op": action, "path": path, "content": content, "old_content": old_content}


def _ws_write(workspace, rel_path, content):
    full = os.path.join(workspace, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


# R7-A
def test_r7a():
    ops = [_mk_op("modify", "README.md", "# ShopFlow\n\nUpdated docs.", "# ShopFlow\n\nOld docs.")]
    ctx = _mk_ctx(ops)
    p = VerificationGovernor(ctx).analyze_impact()
    assert p.get("analysis_failed", False) is False
    assert p.get("scope") == "cosmetic"
    assert p.get("risk_level") == "low"
    assert "markdown_change" in p.get("signals", [])


# R7-B
def test_r7b():
    old = 'def greet(name: str) -> str:\n    """Hello."""\n    return f"Hello {name}"\n'
    new = 'def greet(name: str) -> str:\n    """Greet warmly."""\n    return f"Hello {name}"\n'
    ws = tempfile.mkdtemp(prefix="r7b_")
    _ws_write(ws, "greet.py", old)
    ops = [_mk_op("modify", "greet.py", new, old)]
    ctx = _mk_ctx(ops, ws=ws)
    ctx["initial_file_ops"] = ops
    p = VerificationGovernor(ctx).analyze_impact()
    assert p.get("analysis_failed", False) is False
    assert p.get("scope") == "cosmetic"
    assert p.get("risk_level") == "low"
    assert "docstring_only" in p.get("signals", [])


# R7-C
def test_r7c():
    old = 'def create_order(db: Session, data: dict) -> dict:\n    """Old."""\n    return {}\n'
    new = 'def create_order(db: Session, data: dict, user_id: int) -> dict:\n    """New."""\n    return {}\n'
    ws = tempfile.mkdtemp(prefix="r7c_")
    _ws_write(ws, "orders.py", new)
    ops = [_mk_op("modify", "orders.py", new, old)]
    ctx = _mk_ctx(ops, ws=ws)
    ctx["initial_file_ops"] = ops
    p = VerificationGovernor(ctx).analyze_impact()
    assert p.get("analysis_failed", False) is False
    assert p.get("scope") == "module"
    assert p.get("risk_level") == "medium"
    assert "function_signature" in p.get("signals", [])


# R7-D
def test_r7d():
    old = 'from pydantic import BaseModel\nclass OrderSchema(BaseModel):\n    id: int\n    item: str\n'
    new = 'from pydantic import BaseModel\nclass OrderSchema(BaseModel):\n    id: int\n    item: str\n    quantity: int\n'
    ws = tempfile.mkdtemp(prefix="r7d_")
    _ws_write(ws, "schemas.py", new)
    ops = [_mk_op("modify", "schemas.py", new, old)]
    ctx = _mk_ctx(ops, ws=ws)
    ctx["initial_file_ops"] = ops
    p = VerificationGovernor(ctx).analyze_impact()
    assert p.get("analysis_failed", False) is False
    assert "schema_change" in p.get("signals", [])
    assert p.get("risk_level") == "high"


# R7-E
def test_r7e():
    ws = tempfile.mkdtemp(prefix="r7e_")
    files = {
        "routers/products.py": 'from fastapi import APIRouter\nrouter = APIRouter()\n\n@router.get("/products")\ndef list_products():\n    return []\n',
        "services/product_service.py": 'def get_products():\n    return []\n',
        "services/inventory_service.py": 'def check_stock(item_id: int) -> bool:\n    return True\n',
        "models/product.py": 'class Product:\n    pass\n',
        "schemas/product_schema.py": 'class ProductSchema:\n    pass\n',
        "utils/helpers.py": 'def format_price(price: float) -> str:\n    return f"${price}"\n',
    }
    ops = []
    for rp, c in files.items():
        _ws_write(ws, rp, c)
        ops.append(_mk_op("create", rp, c, ""))
    ctx = _mk_ctx(ops, ws=ws)
    ctx["initial_file_ops"] = ops
    p = VerificationGovernor(ctx).analyze_impact()
    assert p.get("analysis_failed", False) is False
    assert p.get("scope") == "wide"
    assert p.get("risk_level") == "high"
    assert len(p.get("changed_files", [])) >= 5
    assert p.get("file_categories", {}).get("python", 0) >= 5


# Shadow: no modify
def test_shadow_no_modify():
    ops = [_mk_op("modify", "README.md", "# New", "# Old")]
    ctx = _mk_ctx(ops)
    orig_keys = set(ctx.keys())
    orig_meta = set(ctx["meta"].keys())
    VerificationGovernor(ctx).analyze_impact()
    assert set(ctx.keys()) == orig_keys
    assert orig_meta.issubset(set(ctx.get("meta", {}).keys()))
    assert "verification_governance" in ctx.get("meta", {})


# Shadow: analysis failed
def test_shadow_failed():
    ctx = _mk_ctx([])
    ctx["final_file_ops"] = "not_a_list"
    ctx["meta"] = None
    gov = VerificationGovernor(ctx)
    p = gov.analyze_impact()
    assert p.get("analysis_failed") is True
    assert "error" in p


# Shadow: no file ops
def test_shadow_no_ops():
    ctx = _mk_ctx([])
    ctx["final_file_ops"] = []
    p = VerificationGovernor(ctx).analyze_impact()
    assert p.get("analysis_failed", False) is False
    assert p.get("scope") == "none"
    assert p.get("risk_level") == "low"


# API surface
def test_api_surface():
    ws = tempfile.mkdtemp(prefix="api_")
    content = 'from fastapi import APIRouter\n\nrouter = APIRouter()\n\n@router.get("/orders")\ndef list_orders():\n    return []\n'
    _ws_write(ws, "routers/orders.py", content)
    ops = [_mk_op("create", "routers/orders.py", content, "")]
    ctx = _mk_ctx(ops, ws=ws)
    p = VerificationGovernor(ctx).analyze_impact()
    assert p.get("analysis_failed", False) is False
    assert "api_surface_change" in p.get("signals", [])
    assert p.get("risk_level") == "high"


# Audit
def test_audit():
    ops = [_mk_op("modify", "app.py", 'def main():\n    print("v2")', 'def main():\n    print("v1")')]
    ctx = _mk_ctx(ops)
    VerificationGovernor(ctx).analyze_impact()
    rec = ctx.get("meta", {}).get("verification_governance", {})
    assert rec.get("impact_profile") is not None
    assert rec.get("governor_version") == "1.0.0-shadow"
    assert rec.get("shadow_mode") is True


if __name__ == "__main__":
    tests = [
        ("R7-A Markdown only", test_r7a),
        ("R7-B Docstring only", test_r7b),
        ("R7-C Function signature", test_r7c),
        ("R7-D Schema change", test_r7d),
        ("R7-E Wide change", test_r7e),
        ("Shadow: no modify context", test_shadow_no_modify),
        ("Shadow: analysis failed", test_shadow_failed),
        ("Shadow: no file ops", test_shadow_no_ops),
        ("API surface new file", test_api_surface),
        ("Audit record", test_audit),
    ]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print("  PASS  " + name)
            passed += 1
        except AssertionError as e:
            print("  FAIL  " + name + ": " + str(e))
            failed += 1
        except Exception as e:
            print("  ERROR " + name + ": " + str(e))
            failed += 1
    print(f"\n{'='*60}")
    print(f"  Results: {passed} passed  {failed} failed")
    print(f"{'='*60}")