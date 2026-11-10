# -*- coding: utf-8 -*-
# test_verification_governor.py
# Shadow Mode 单元验证 — 独立于 Worker 执行链
# 用法: python test_verification_governor.py

import sys
sys.path.insert(0, "..")

# 直接导入避免 __init__.py 的完整依赖链
import importlib.util, os
_governor_path = os.path.join(
    os.path.dirname(__file__), "..",
    "agents", "qwen", "step_executor", "verification_governor.py",
)
_spec = importlib.util.spec_from_file_location("verification_governor", _governor_path)
_vg_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vg_mod)

VerificationGovernor = _vg_mod.VerificationGovernor
_safe_parse = _vg_mod._safe_parse
_extract_function_names = _vg_mod._extract_function_names
_extract_class_names = _vg_mod._extract_class_names
_extract_decorator_names = _vg_mod._extract_decorator_names
_compare_ast_symbols = _vg_mod._compare_ast_symbols
_is_docstring_only_change = _vg_mod._is_docstring_only_change
_check_schema_file = _vg_mod._check_schema_file
_path_to_module = _vg_mod._path_to_module

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}  {detail}")


# ================================================================
#  Test 1: AST 工具函数
# ================================================================
print("\n── Test 1: AST utilities ──")

tree = _safe_parse("def foo():\n    pass\nclass Bar:\n    pass\n")
check("parse ok", tree is not None)

funcs = _extract_function_names(tree)
check("funcs", funcs == {"foo"}, str(funcs))

classes = _extract_class_names(tree)
check("classes", classes == {"Bar"}, str(classes))

decos = _extract_decorator_names(
    _safe_parse(
        "from fastapi import APIRouter\nrouter = APIRouter()\n\n"
        "@router.post('/x')\ndef create():\n    pass\n"
    )
)
check("decorators", "post" in decos, str(decos))

changes = _compare_ast_symbols(
    "def old_func():\n    pass\n",
    "def new_func():\n    pass\n",
)
check("symbol diff", changes == {"old_func", "new_func"}, str(changes))

# ================================================================
#  Test 2: Docstring-only 检测
# ================================================================
print("\n── Test 2: Docstring-only detection ──")

old2 = 'def greet(name: str) -> str:\n    """Old."""\n    return f"Hello, {name}"\n'
new2 = 'def greet(name: str) -> str:\n    """New doc with more detail."""\n    return f"Hello, {name}"\n'
old_tree = _safe_parse(old2)
new_tree = _safe_parse(new2)
check("docstring only", _is_docstring_only_change(
    old_tree, new_tree, {"greet"}, {"greet"}
))

old3 = 'def greet(name: str) -> str:\n    """Old."""\n    return f"Hello, {name}"\n'
new3 = 'def greet(name: str, title: str = "") -> str:\n    """New."""\n    return f"Hello, {title} {name}"\n'
old_tree3 = _safe_parse(old3)
new_tree3 = _safe_parse(new3)
# Different body but same function name → should NOT be docstring only
check("not docstring only (body changed)",
      not _is_docstring_only_change(old_tree3, new_tree3, {"greet"}, {"greet"}))

# ================================================================
#  Test 3: Schema 检测
# ================================================================
print("\n── Test 3: Schema detection ──")

check("schema by filename",
      _check_schema_file(_safe_parse("x = 1"), "backend/models/order.py"))

check("schema by BaseModel",
      _check_schema_file(
          _safe_parse("from pydantic import BaseModel\nclass Order(BaseModel):\n    pass"),
          "any.py",
      ))

check("not schema",
      not _check_schema_file(_safe_parse("x = 1"), "utils/helpers.py"))

# ================================================================
#  Test 4: Module path conversion
# ================================================================
print("\n── Test 4: Module path conversion ──")

check("path to module",
      _path_to_module("backend/routers/orders.py") == "backend.routers.orders")

check("__init__ path",
      _path_to_module("backend/__init__.py") == "backend")

check("no extension path",
      _path_to_module("README.md") == "README.md", str(_path_to_module("README.md")))

# ================================================================
#  Test 5: R7-A — Markdown only
# ================================================================
print("\n── Test 5: R7-A Markdown only ──")

vg5 = VerificationGovernor({
    "workspace_info": {"path": "."},
    "final_file_ops": [
        {"path": "docs/api.md", "op": "modify", "content": "# Updated Docs"},
    ],
})
p5 = vg5.analyze_impact()
check("scope=cosmetic", p5["scope"] == "cosmetic", p5["scope"])
check("risk=low", p5["risk_level"] == "low", p5["risk_level"])
check("markdown_change signal", "markdown_change" in p5["signals"], str(p5["signals"]))

# ================================================================
#  Test 6: R7-B — Docstring only
# ================================================================
print("\n── Test 6: R7-B Docstring only ──")

# Inject old content directly
vg6 = VerificationGovernor({
    "workspace_info": {"path": "."},
    "final_file_ops": [
        {
            "path": "utils/greet.py", "op": "modify",
            "content": 'def greet(name: str) -> str:\n    """New."""\n    return f"Hello, {name}"\n',
            "old_content": 'def greet(name: str) -> str:\n    """Old."""\n    return f"Hello, {name}"\n',
        },
    ],
})
p6 = vg6.analyze_impact()
check("docstring_only signal", "docstring_only" in p6["signals"], str(p6["signals"]))
check("cosmetic scope", p6["scope"] == "cosmetic", p6["scope"])
check("risk=low", p6["risk_level"] == "low", p6["risk_level"])

# ================================================================
#  Test 7: R7-C — Function signature change
# ================================================================
print("\n── Test 7: R7-C Function signature change ──")

vg7 = VerificationGovernor({
    "workspace_info": {"path": "."},
    "final_file_ops": [
        {
            "path": "backend/routers/orders.py", "op": "modify",
            "content": 'def create_order(db: Session, data: dict, user_id: int) -> dict:\n    """New."""\n    return {}\n',
            "old_content": 'def create_order(db: Session, data: dict) -> dict:\n    """Old."""\n    return {}\n',
        },
    ],
})
p7 = vg7.analyze_impact()
check("function_signature signal",
      "function_signature" in p7["signals"], str(p7["signals"]))
check("risk=medium", p7["risk_level"] == "medium", p7["risk_level"])
check("scope=module", p7["scope"] == "module", p7["scope"])

# ================================================================
#  Test 8: R7-D — Schema change
# ================================================================
print("\n── Test 8: R7-D Schema change ──")

vg8 = VerificationGovernor({
    "workspace_info": {"path": "."},
    "final_file_ops": [
        {
            "path": "backend/models/order.py", "op": "modify",
            "content": 'from pydantic import BaseModel\n\nclass OrderCreate(BaseModel):\n    customer_name: str\n',
            "old_content": 'import datetime\n',
        },
    ],
})
p8 = vg8.analyze_impact()
check("schema_change signal", "schema_change" in p8["signals"], str(p8["signals"]))
check("risk=high", p8["risk_level"] == "high", p8["risk_level"])

# ================================================================
#  Test 9: R7-E — Wide change
# ================================================================
print("\n── Test 9: R7-E Wide change ──")

vg9 = VerificationGovernor({
    "workspace_info": {"path": "."},
    "final_file_ops": [
        {"path": "backend/routers/orders.py", "op": "modify",
         "content": 'def create():\n    pass\n', "old_content": ""},
        {"path": "backend/models/order.py", "op": "modify",
         "content": 'class Order:\n    pass\n', "old_content": ""},
        {"path": "backend/schemas/order.py", "op": "modify",
         "content": 'class OrderSchema:\n    pass\n', "old_content": ""},
        {"path": "backend/services/order.py", "op": "modify",
         "content": 'def process():\n    pass\n', "old_content": ""},
        {"path": "backend/services/notification.py", "op": "modify",
         "content": 'def notify():\n    pass\n', "old_content": ""},
        {"path": "tests/test_orders.py", "op": "modify",
         "content": 'def test():\n    pass\n', "old_content": ""},
    ],
})
p9 = vg9.analyze_impact()
check("scope=wide", p9["scope"] == "wide", p9["scope"])
check("risk=high", p9["risk_level"] == "high", p9["risk_level"])
check("file_categories python=6",
      p9["file_categories"].get("python", 0) == 6,
      str(p9["file_categories"]))

# ================================================================
#  Test 10: Edge cases
# ================================================================
print("\n── Test 10: Edge cases ──")

# Empty final_file_ops
vg10a = VerificationGovernor({
    "workspace_info": {"path": "."},
    "final_file_ops": [],
})
p10a = vg10a.analyze_impact()
check("empty → scope=none", p10a["scope"] == "none", p10a["scope"])
check("empty → risk=low", p10a["risk_level"] == "low", p10a["risk_level"])

# Syntax error
vg10b = VerificationGovernor({
    "workspace_info": {"path": "."},
    "final_file_ops": [
        {"path": "broken.py", "op": "create", "content": "def foo(:"},
    ],
})
p10b = vg10b.analyze_impact()
check("syntax error → signal", "syntax_error" in p10b["signals"], str(p10b["signals"]))
check("syntax error → risk=high", p10b["risk_level"] == "high", p10b["risk_level"])

# No context at all
vg10c = VerificationGovernor({})
p10c = vg10c.analyze_impact()
check("no context → scope=none", p10c["scope"] == "none", p10c["scope"])

# API surface change (route decorator)
vg10d = VerificationGovernor({
    "workspace_info": {"path": "."},
    "final_file_ops": [
        {
            "path": "backend/routers/orders.py", "op": "create",
            "content": (
                "from fastapi import APIRouter\n"
                "router = APIRouter()\n\n"
                "@router.post('/orders')\n"
                "def create_order():\n    pass\n"
            ),
        },
    ],
})
p10d = vg10d.analyze_impact()
check("api surface → risk=high",
      p10d["risk_level"] == "high",
      f"risk={p10d['risk_level']} signals={p10d['signals']}")

# ================================================================
#  Summary
# ================================================================
print(f"\n{'='*60}")
print(f"  Results: {PASS} passed, {FAIL} failed")
print(f"{'='*60}")
if FAIL > 0:
    sys.exit(1)