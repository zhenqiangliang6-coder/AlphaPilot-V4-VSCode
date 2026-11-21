# python_worker/tests/test_g1042_contracts.py
"""G10.42 结构契约守卫（端点集合 / 禁止模型 / router 禁用直连 db）契约测试。

真实故障（shopflow_v21_1，2026-11-15 19:42）：
`2 failed, 5 passed in 1073.72s`，R5–R9 五轮四维全绿，R10 质量维红：

    Router clean: False（backend/routers/inventory.py 命中 db.query(）
    语义契约: [imports] backend/schemas/order.py: 使用了禁止模型 OrderItem;
      [router_contract] orders: 缺失端点 DELETE /{order_id}、GET /、
      GET /{order_id}、PUT /{order_id}/status；存在额外端点
      PATCH /{order_id}/status

R10 把受保护路由 orders.py 退化成内存字典实现（5 端点 → 只剩 POST /
与 PATCH /{order_id}/status），引入禁止模型 OrderItem，inventory 路由残留
db.query(。服务层符号齐全、pytest 仍绿 ⇒ 闸门基于失败数的收敛判定无
信号 ⇒ 假绿放行，直到 R10 质量门 FAIL-CLOSED 才暴露。G10.39（断裂 import）
/G10.41（空壳化）只覆盖语法与资产蒸发，放行前没有校验这类「题面冻结的
结构契约」。

契约：守卫必须在 build_candidate 之前**就地**修正 final_file_ops
（FAIL-CLOSED，成长法第 35 条），端点集合 / 禁止模型 / router 禁用直连
db 三类违约要么恢复合规基线、要么拒绝该 op；新建文件 / delete /
_internal / 路径越界 / 合规 op / 基线本身违约的修复 op 一律不误伤。
"""

import ast
import importlib.util
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import python_worker.delivery_gate as dg  # noqa: E402
from python_worker.delivery_gate import (  # noqa: E402
    build_candidate,
    restore_contract_violating_ops,
)


def _load_observe_module():
    """从绝对路径加载判卷侧模块，取其冻结契约做「防漂移」比对。

    只 import（执行模块级常量/函数定义），不触发任何 pytest 收集或测试。
    """
    path = Path(__file__).with_name("test_observe_task_system.py")
    spec = importlib.util.spec_from_file_location("_g1042_observe_contract", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── v21 真实 R10 交付清单（shopflow_v21_1 落盘产物，逐字快照）────────

R10_ORDERS = '''from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from backend.schemas.order import OrderCreate, OrderUpdate, OrderResponse
from backend.models.enums import OrderStatus
from backend.models.order import Order
from backend.models.inventory import Inventory
from backend.database import get_db

router = APIRouter()

orders_db = {
    1: {"id": 1, "item_name": "Laptop", "quantity": 1, "status": OrderStatus.pending}
}

@router.post("/", response_model=OrderResponse)
def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    if not order.items:
        order_id = len(orders_db) + 1
        new_order = {
            "id": order_id,
            "user_id": order.user_id,
            "total_amount": order.total_amount,
            "items": [],
            "item_name": order.item_name,
            "quantity": order.quantity,
            "status": OrderStatus.pending
        }
        orders_db[order_id] = new_order
        return new_order

    for item in order.items:
        inv = db.query(Inventory).filter(Inventory.product_name == item.product_name).first()
        if not inv:
            raise HTTPException(status_code=400, detail=f"Product {item.product_name} does not exist in inventory")
        if inv.quantity < item.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for {item.product_name}")

    for item in order.items:
        inv = db.query(Inventory).filter(Inventory.product_name == item.product_name).first()
        inv.quantity -= item.quantity
    db.commit()

    order_id = len(orders_db) + 1
    new_order = {
        "id": order_id,
        "user_id": order.user_id,
        "total_amount": order.total_amount,
        "items": [{"product_name": i.product_name, "quantity": i.quantity} for i in order.items],
        "item_name": order.item_name,
        "quantity": order.quantity,
        "status": OrderStatus.pending
    }
    orders_db[order_id] = new_order
    return new_order

@router.patch("/{order_id}/status", response_model=OrderResponse)
def update_order_status(order_id: int, payload: OrderUpdate):
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail="Order not found")

    order = orders_db[order_id]
    current_status = order["status"]

    if payload.status not in current_status.next_states():
        raise HTTPException(status_code=422, detail="Invalid status transition")

    order["status"] = payload.status
    return order
'''

R10_INVENTORY = '''from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List

from backend.database import get_db
from backend.models.inventory import Inventory
from backend.schemas.inventory import InventoryCreate, InventoryUpdate, InventoryResponse

router = APIRouter()

@router.post("/", response_model=InventoryResponse)
def create_inventory(item: InventoryCreate, db: Session = Depends(get_db)):
    db_item = Inventory(
        product_name=item.product_name,
        sku=item.sku,
        quantity=item.quantity,
        unit_price=item.unit_price
    )
    db.add(db_item)
    try:
        db.commit()
        db.refresh(db_item)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Product already exists")
    return db_item

@router.get("/", response_model=List[InventoryResponse])
def list_inventory(db: Session = Depends(get_db)):
    return db.query(Inventory).all()

@router.get("/{product_name}", response_model=InventoryResponse)
def get_inventory(product_name: str, db: Session = Depends(get_db)):
    db_item = db.query(Inventory).filter(Inventory.product_name == product_name).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Product not found")
    return db_item

@router.patch("/{product_name}", response_model=InventoryResponse)
def update_inventory(product_name: str, item: InventoryUpdate, db: Session = Depends(get_db)):
    db_item = db.query(Inventory).filter(Inventory.product_name == product_name).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Product not found")

    update_data = item.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_item, key, value)

    db.commit()
    db.refresh(db_item)
    return db_item
'''

R10_SCHEMAS_ORDER = '''from pydantic import BaseModel
from typing import List, Optional
from backend.models.enums import OrderStatus

class OrderItem(BaseModel):
    product_name: str
    quantity: int

class OrderCreate(BaseModel):
    user_id: Optional[str] = None
    total_amount: Optional[float] = None
    items: Optional[List[OrderItem]] = None
    item_name: Optional[str] = None
    quantity: Optional[int] = None

class OrderUpdate(BaseModel):
    status: OrderStatus

class OrderResponse(BaseModel):
    id: int
    user_id: Optional[str] = None
    total_amount: Optional[float] = None
    items: Optional[List[dict]] = None
    item_name: Optional[str] = None
    quantity: Optional[int] = None
    status: OrderStatus
'''


# ── 合规基线（R9 结束态的等价形态）────────────────────────────────
# orders.py 在 R6/R8 的合规基线本就直连 db（服务层 R10 才引入），
# 因此守卫绝不能对 orders.py 查 db.query( —— 这组数据用于证明不误伤。

BASE_ORDERS = '''from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.order import Order

router = APIRouter()

@router.post("/", status_code=status.HTTP_200_OK)
def create_order(db: Session = Depends(get_db)):
    return db.query(Order).all()

@router.get("/", status_code=200)
def list_orders(db: Session = Depends(get_db)):
    return db.query(Order).all()

@router.get("/{order_id}", status_code=200)
def get_order(order_id: str, db: Session = Depends(get_db)):
    return db.query(Order).get(order_id)

@router.put("/{order_id}/status", status_code=200)
def update_status(order_id: str, db: Session = Depends(get_db)):
    return db.query(Order).get(order_id)

@router.delete("/{order_id}", status_code=204)
def delete_order(order_id: str, db: Session = Depends(get_db)):
    return None
'''

BASE_INVENTORY = '''from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.services.inventory_service import InventoryService

router = APIRouter()

@router.post("/", status_code=200)
def create_inventory(db: Session = Depends(get_db)):
    return InventoryService(db).create_inventory()

@router.get("/", status_code=200)
def list_inventory(db: Session = Depends(get_db)):
    return InventoryService(db).get_inventory_list()

@router.get("/{product_name}", status_code=200)
def get_inventory(product_name: str, db: Session = Depends(get_db)):
    return InventoryService(db).get_inventory(product_name)

@router.patch("/{product_name}", status_code=200)
def update_inventory(product_name: str, db: Session = Depends(get_db)):
    return InventoryService(db).update_inventory(product_name)
'''

BASE_SCHEMAS_ORDER = '''from pydantic import BaseModel
from typing import List, Optional

class OrderCreate(BaseModel):
    items: Optional[List[dict]] = None

class OrderUpdateStatus(BaseModel):
    new_status: str

class OrderResponse(BaseModel):
    id: int
'''

# R8 遗留形态：端点合规但路由仍直连 db（R8 未引入服务层，属正常）。
# 这是「基线本身就不合契约」的真实场景，用于验证拒绝分支与不误伤。
BASE_INVENTORY_R8 = '''from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.inventory import Inventory

router = APIRouter()

@router.post("/", status_code=200)
def create_inventory(db: Session = Depends(get_db)):
    db.add(Inventory())
    return None

@router.get("/", status_code=200)
def list_inventory(db: Session = Depends(get_db)):
    return db.query(Inventory).all()

@router.get("/{product_name}", status_code=200)
def get_inventory(product_name: str, db: Session = Depends(get_db)):
    return db.query(Inventory).first()

@router.patch("/{product_name}", status_code=200)
def update_inventory(product_name: str, db: Session = Depends(get_db)):
    return db.query(Inventory).first()
'''


# R10 服务层重构轮题面（触发 G10.42 的显式约束信号）
_R10_REQ = (
    "重构 ShopFlow 后端：把路由中的业务逻辑提取到服务层。\n"
    "端点集合必须精确为（不得新增/删除任何端点）：POST / 返回 200。\n"
    "不得包含以下调用：db.query(, db.add(, db.commit(。\n"
    "禁止 import 或定义不存在的 ORM 模型：OrderItem。\n"
)

# 非重构轮题面（R7 简单增量）—— 守卫必须完全不介入
_PLAIN_REQ = "给订单模块补一点日志，保持现有行为。"


def _base():
    return {
        "backend/routers/orders.py": BASE_ORDERS,
        "backend/routers/inventory.py": BASE_INVENTORY,
        "backend/schemas/order.py": BASE_SCHEMAS_ORDER,
    }


def _r10_ops():
    """v21 真实 R10 交付清单：3 个违约重写 + 1 个合规新建（不介入）。"""
    return [
        {"op": "modify", "path": "backend/routers/orders.py", "content": R10_ORDERS},
        {"op": "modify", "path": "backend/routers/inventory.py", "content": R10_INVENTORY},
        {"op": "modify", "path": "backend/schemas/order.py", "content": R10_SCHEMAS_ORDER},
        {"op": "create", "path": "backend/services/order_service.py",
         "content": "class OrderService:\n    pass\n"},
    ]


# ── 1. 冻结契约镜像与判卷侧一致（防两套判定漂移）──────────────────

def test_contract_mirror_matches_judging_suite():
    obs = _load_observe_module()
    sc = obs.SERVICE_LAYER_CONTRACT
    for name, expected in sc["router_contract"].items():
        got = dg._G1042_ROUTER_CONTRACT[name]
        assert got == [(e["method"], e["path"], e["status_code"])
                       for e in expected], name
    assert set(dg._G1042_FORBIDDEN_MODELS) == set(sc["forbidden_imports"])
    assert tuple(dg._G1042_ROUTER_FORBIDDEN) == tuple(sc["router_forbidden"])


def test_endpoint_extraction_matches_judging_suite():
    """生产侧 _g1042_router_endpoints 与判卷侧 _extract_router_endpoints 一致。"""
    obs = _load_observe_module()
    samples = [
        BASE_ORDERS, BASE_INVENTORY, BASE_INVENTORY_R8,
        R10_ORDERS, R10_INVENTORY,
        # @router.post("") 归一为 "/" 的语义等价写法
        'from fastapi import APIRouter\nrouter = APIRouter()\n'
        '@router.post("", status_code=201)\ndef a(): pass\n'
        '@router.get("/")\ndef b(): pass\n',
    ]
    for src in samples:
        canonical = {k: v["status_code"]
                     for k, v in obs._extract_router_endpoints(ast.parse(src)).items()}
        assert dg._g1042_router_endpoints(src) == canonical


# ── 2. 三类违约的检出 ─────────────────────────────────────────────

def test_compliant_baseline_has_no_violations():
    for path, src in _base().items():
        assert dg._g1042_contract_violations(path, src) == [], path


def test_detects_missing_endpoints():
    v = dg._g1042_contract_violations("backend/routers/orders.py", R10_ORDERS)
    assert any("缺失端点 DELETE /{order_id}" in x for x in v)
    assert any("缺失端点 GET /" in x for x in v)
    assert any("缺失端点 PUT /{order_id}/status" in x for x in v)


def test_detects_extra_patch_endpoint():
    v = dg._g1042_contract_violations("backend/routers/orders.py", R10_ORDERS)
    assert any("存在额外端点 PATCH /{order_id}/status" in x for x in v)


def test_detects_status_code_mismatch():
    src = BASE_ORDERS.replace(
        '@router.delete("/{order_id}", status_code=204)',
        '@router.delete("/{order_id}", status_code=200)')
    v = dg._g1042_contract_violations("backend/routers/orders.py", src)
    assert any("状态码 200 != 204" in x for x in v)


def test_detects_forbidden_model_in_schemas():
    v = dg._g1042_contract_violations("backend/schemas/order.py", R10_SCHEMAS_ORDER)
    assert any("禁止" in x and "OrderItem" in x for x in v)


def test_detects_forbidden_model_import_and_bare_use():
    # from-import 命中别名（与判卷侧 _check_imports 一致）
    assert any("OrderItem" in x for x in dg._g1042_contract_violations(
        "backend/models/order.py", "from x import OrderItem\n"))
    # ast.Import 只检顶层名（alias.name.split(".")[0]）：import OrderItem 命中
    assert any("OrderItem" in x for x in dg._g1042_contract_violations(
        "backend/models/order.py", "import OrderItem\n"))
    # 深层 import 两段都不命中 —— 与判卷侧一致，绝不擅自加严
    assert dg._g1042_contract_violations(
        "backend/models/order.py", "import backend.models.OrderItem\n") == []
    # 裸用禁止模型（未 import 直接引用）命中
    assert any("OrderItem" in x for x in dg._g1042_contract_violations(
        "backend/models/order.py", "def f():\n    return OrderItem()\n"))


def test_detects_inventory_db_query():
    v = dg._g1042_contract_violations("backend/routers/inventory.py", R10_INVENTORY)
    assert any("禁用调用 db.query(" in x for x in v)


def test_orders_db_query_is_not_flagged():
    """orders.py 合规基线直连 db，不得被 db 守卫误伤（服务层 R10 才引入）。"""
    assert "db.query(" in BASE_ORDERS
    assert dg._g1042_contract_violations(
        "backend/routers/orders.py", BASE_ORDERS) == []


def test_unparseable_router_is_flagged_not_guessed():
    v = dg._g1042_contract_violations(
        "backend/routers/orders.py", "def broken(:\n  pass\n")
    assert any("不可判定" in x for x in v)


# ── 3. 恢复 / 拒绝与就地改 op ─────────────────────────────────────

def test_restores_compliant_baseline_in_place():
    base, ops = _base(), _r10_ops()
    restored, rejected = restore_contract_violating_ops(ops, base, _R10_REQ)
    assert set(restored) == {
        "backend/routers/orders.py", "backend/routers/inventory.py",
        "backend/schemas/order.py",
    }
    assert rejected == []
    # 必须就地改 op：候选区恢复而落盘清单仍违约属半成品修复
    by_path = {o["path"]: o for o in ops}
    for p in restored:
        assert by_path[p]["content"] == base[p]
    # 新建的合规 service 不被介入
    assert by_path["backend/services/order_service.py"]["content"] == \
        "class OrderService:\n    pass\n"


def test_delivery_manifest_matches_verified_candidate():
    """成长法第 35 条：最终落盘清单与已验证候选同源。"""
    base, ops = _base(), _r10_ops()
    restore_contract_violating_ops(ops, base, _R10_REQ)
    delivered = build_candidate(base, ops)
    assert delivered["backend/routers/orders.py"] == BASE_ORDERS
    assert delivered["backend/routers/inventory.py"] == BASE_INVENTORY
    assert delivered["backend/schemas/order.py"] == BASE_SCHEMAS_ORDER
    assert "OrderItem" not in delivered["backend/schemas/order.py"]
    assert "db.query(" not in delivered["backend/routers/inventory.py"]
    # _apply_back 遇 base == content 会跳过回写，故 op 本身必须已合规
    context = {"final_file_ops": ops}
    dg._apply_back(context, delivered, base)
    for op in context["final_file_ops"]:
        p = str(op.get("path") or "").replace("\\", "/")
        if p in base:
            assert op["content"] == base[p], p


def test_rejects_op_when_baseline_also_violates():
    """R8 遗留 inventory.py 含 db.query(，R10 重写仍违规 → 拒绝该 op。"""
    base = {"backend/routers/inventory.py": BASE_INVENTORY_R8}
    ops = [{"op": "modify", "path": "backend/routers/inventory.py",
            "content": R10_INVENTORY}]
    restored, rejected = restore_contract_violating_ops(ops, base, _R10_REQ)
    assert restored == []
    assert rejected == ["backend/routers/inventory.py"]
    assert ops == []  # 违约 op 已从落盘清单移除（FAIL-CLOSED）


# ── 4. 不误伤边界 ─────────────────────────────────────────────────

def test_new_file_not_touched():
    base = _base()
    ops = [{"op": "create", "path": "backend/routers/inventory.py",
            "content": R10_INVENTORY}]
    base.pop("backend/routers/inventory.py")
    assert restore_contract_violating_ops(ops, base, _R10_REQ) == ([], [])
    assert ops[0]["content"] == R10_INVENTORY


def test_compliant_op_not_touched():
    base, ops = _base(), [
        {"op": "modify", "path": "backend/routers/orders.py", "content": BASE_ORDERS},
    ]
    assert restore_contract_violating_ops(ops, base, _R10_REQ) == ([], [])
    assert ops[0]["content"] == BASE_ORDERS


def test_baseline_violating_but_compliant_op_not_touched():
    """把坏基线改好的合规 op 不该被误伤。"""
    base = {"backend/routers/inventory.py": BASE_INVENTORY_R8}
    ops = [{"op": "modify", "path": "backend/routers/inventory.py",
            "content": BASE_INVENTORY}]
    assert restore_contract_violating_ops(ops, base, _R10_REQ) == ([], [])
    assert ops[0]["content"] == BASE_INVENTORY


def test_delete_and_internal_ops_not_touched():
    base = _base()
    ops = [
        {"op": "delete", "path": "backend/routers/orders.py", "content": R10_ORDERS},
        {"op": "modify", "path": "backend/routers/orders.py",
         "content": R10_ORDERS, "_internal": True},
    ]
    assert restore_contract_violating_ops(ops, base, _R10_REQ) == ([], [])
    assert all(o["content"] == R10_ORDERS for o in ops)


def test_path_traversal_and_out_of_scope_ignored():
    base = _base()
    ops = [
        {"op": "modify", "path": "../backend/routers/orders.py", "content": R10_ORDERS},
        {"op": "modify", "path": "/abs/backend/routers/orders.py", "content": R10_ORDERS},
        {"op": "modify", "path": "docs/readme.md", "content": R10_ORDERS},
        {"op": "modify", "path": "tests/test_orders.py", "content": R10_ORDERS},
    ]
    assert restore_contract_violating_ops(ops, base, _R10_REQ) == ([], [])


def test_windows_style_paths_are_normalized():
    base, ops = _base(), [
        {"op": "modify", "path": "backend\\routers\\orders.py", "content": R10_ORDERS},
    ]
    restored, _ = restore_contract_violating_ops(ops, base, _R10_REQ)
    assert restored == ["backend/routers/orders.py"]
    assert ops[0]["content"] == BASE_ORDERS


def test_non_refactor_round_not_touched():
    """非服务层重构轮（R7 简单增量）完全不介入，防误伤既有闸门行为。

    回归 test_g1034_contracts.py::test_selfcontained_full_ops_are_not_rolled_back：
    其 user_request 只是「补一点日志」，守卫若无条件介入会拒绝 orders.py op、
    改变 final_file_ops，导致 gate 走分层收敛而非 full_selfcontained_delivery。
    """
    assert dg._g1042_refactor_round(_PLAIN_REQ) is False
    assert dg._g1042_refactor_round(_R10_REQ) is True
    assert dg._g1042_refactor_round("") is False
    base, ops = _base(), _r10_ops()
    assert restore_contract_violating_ops(ops, base, _PLAIN_REQ) == ([], [])
    by_path = {o["path"]: o for o in ops}
    # 违约 op 原样保留，未被就地改、未被拒绝
    assert by_path["backend/routers/orders.py"]["content"] == R10_ORDERS
    assert len(ops) == 4


# ── 5. v21 真实 R10 清单端到端修复验证 ────────────────────────────

def test_v21_r10_manifest_end_to_end_repair():
    """用 v21 真实 R10 三份坏生成物 + 合规基线做端到端修复。"""
    base, ops = _base(), _r10_ops()
    # 违约确实存在（还原故障前提）
    assert any("缺失端点" in x for x in dg._g1042_contract_violations(
        "backend/routers/orders.py", R10_ORDERS))
    assert any("OrderItem" in x for x in dg._g1042_contract_violations(
        "backend/schemas/order.py", R10_SCHEMAS_ORDER))
    assert any("db.query(" in x for x in dg._g1042_contract_violations(
        "backend/routers/inventory.py", R10_INVENTORY))

    restored, rejected = restore_contract_violating_ops(ops, base, _R10_REQ)
    assert set(restored) == {
        "backend/routers/orders.py", "backend/routers/inventory.py",
        "backend/schemas/order.py",
    }
    assert rejected == []
    fixed = build_candidate(base, ops)
    # 端点集合回到契约 5 个、禁止模型消失、inventory 不再直连 db
    eps = dg._g1042_router_endpoints(fixed["backend/routers/orders.py"])
    assert set(eps) == {(m, p) for m, p, _ in dg._G1042_ROUTER_CONTRACT["orders"]}
    assert "OrderItem" not in fixed["backend/schemas/order.py"]
    assert "db.query(" not in fixed["backend/routers/inventory.py"]
    for path in restored:
        assert dg._g1042_contract_violations(path, fixed[path]) == [], path


def test_structural_repair_independent_of_pytest_green():
    """核心回归：违约内容不制造 pytest 失败，守卫仍必须恢复（不看失败数）。"""
    from python_worker.delivery_gate import _run_pytest
    base = {
        "backend/routers/orders.py": BASE_ORDERS,
        "tests/test_smoke.py": "def test_ok():\n    assert True\n",
    }
    ops = [{"op": "modify", "path": "backend/routers/orders.py",
            "content": R10_ORDERS}]
    bad = build_candidate(base, ops)
    ok_bad, _ = _run_pytest(bad)
    assert ok_bad is True, "还原故障前提：违约内容不影响 pytest"

    restored, _ = restore_contract_violating_ops(ops, base, _R10_REQ)
    assert restored == ["backend/routers/orders.py"]
    fixed = build_candidate(base, ops)
    assert fixed["backend/routers/orders.py"] == BASE_ORDERS
    ok_fixed, _ = _run_pytest(fixed)
    assert ok_fixed is True
