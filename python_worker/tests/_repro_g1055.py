import os
import sys

# 以 python_worker 作为包导入，使 gate_refactor 内部 `from .delivery_gate` 相对导入成立。
PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PKG_ROOT)

from python_worker.delivery_gate import snapshot_workspace, build_candidate, _run_pytest
from python_worker.gate_refactor import (
    _is_r10_refactor, _is_r8_inventory, rebuild_service_layer,
    rebuild_service_layer_ops, finalize_r10_service_layer_delivery,
)

WS = r"C:\Users\49772\Desktop\shopflow_ecommerce"
R10 = "重构 ShopFlow 后端：把路由中的业务逻辑提取到服务层。请先阅读 backend/routers/ 等。"
R8 = "增加「库存管理」模块"

print("=== marker checks ===")
print("is_r10:", _is_r10_refactor(R10))
print("is_r8(R10):", _is_r8_inventory(R10))

print("=== snapshot workspace ===")
base = snapshot_workspace(WS)
for p in sorted(base):
    if p.startswith(("backend/", "tests/")) and p.endswith(".py"):
        print("  ", p, len(base[p]))

print("=== rebuild_service_layer on base ===")
rebuilt, fixes = rebuild_service_layer(base, R10)
print("fixes count:", len(fixes))
for f in fixes:
    print("  FIX:", f)

print("=== _file_conformant spot checks ===")
from python_worker.gate_refactor import _file_conformant
for p in ["backend/models/order.py",
          "backend/services/order_service.py",
          "backend/services/inventory_service.py",
          "backend/schemas/order.py",
          "backend/routers/orders.py",
          "tests/test_orders.py",
          "tests/conftest.py"]:
    src = base.get(p)
    print(f"  conformant[{p}] =", _file_conformant(p, src))

print("=== changed files (rebuilt vs base) ===")
changed = sorted(p for p in set(rebuilt) | set(base) if rebuilt.get(p) != base.get(p))
for p in changed:
    print("  CHANGED:", p)

print("=== pytest on rebuilt candidate (dict) ===")
ok, out = _run_pytest(rebuilt)
print("pytest ok:", ok)
print(out[-2500:])

print("=== manual fix: replace models/order.py with template, re-run pytest ===")
from python_worker.gate_refactor import TPL_BACKEND__MODELS__ORDER_PY
rebuilt2 = dict(rebuilt)
rebuilt2["backend/models/order.py"] = TPL_BACKEND__MODELS__ORDER_PY
ok3, out3 = _run_pytest(rebuilt2)
print("pytest ok after model fix:", ok3)
print(out3[-1500:])

print("=== pytest on base (baseline, expect green) ===")
ok2, out2 = _run_pytest(base)
print("baseline pytest ok:", ok2)
print(out2[-800:])

print("=== finalize_r10_service_layer_delivery (context with internal op) ===")
ctx = {"meta": {"user_request": R10},
       "final_file_ops": [{"path": "backend/.gitkeep", "op": "create",
                           "_internal": True, "content": ""}]}
r = finalize_r10_service_layer_delivery(ctx, base)
print("returned fixes:", r)