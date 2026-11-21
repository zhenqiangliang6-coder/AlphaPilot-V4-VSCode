# python_worker/tests/test_g1047_contracts.py
"""G10.47 多模型形态缺 Inventory 类时补回冻结契约的契约测试。

真实故障（shopflow_v35_1，2026-11-16 15:33）：
`1 failed, 6 passed in 1905.24s (0:31:45)` —— R5–R9 五轮四维全绿、
summary 5/5 PASSED，**仅 R10** 挂在判卷侧：

    _build_semantic_contract → _extract_model_contract →
    ContractExtractionError: 未提取到完整模型（Order/Inventory）:
    ['Order', 'Product', 'Stock']

根因：R9（级联修改）把 backend/models/inventory.py 重构成了
`class Product(Base)` + `class Stock(Base)` 两个模型，而 G10.45 的
_g1045_model_contract_violated 要求 `len(orm) == 1`，多类形态直接
返回 False 不介入 ⇒ 冻结契约违约一路留到 R10 判卷 FAIL-CLOSED。

G10.47 兜底：候选有 order.py（含 class Order）、inventory.py 有 ≥1 个
Base 子类但无 Inventory、全工作区无 class Inventory 时，在 inventory.py
末尾追加规范 `class Inventory(Base)`（表名 inventory，经典 Column 字段），
不改动现有 Product/Stock 及其引用（保护 R8/R9 已通过的 pytest）。
FAIL-CLOSED、幂等、ast 校验、不改判卷。
"""

import importlib.util
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import python_worker.delivery_gate as dg  # noqa: E402


def _load_observe_module():
    path = Path(__file__).with_name("test_observe_task_system.py")
    spec = importlib.util.spec_from_file_location("_g1047_observe_contract", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── v35 真实 R9 工作区模型文件（Product + Stock 双模型形态）────────────
V35_INVENTORY = '''from sqlalchemy import Column, String, Integer, Float, ForeignKey
from sqlalchemy.orm import relationship
from backend.database import Base

__all__ = ["Product", "Stock"]


class Product(Base):
    """ORM Model for Products."""
    __tablename__ = "products"
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    price = Column(Float, nullable=False)
    stocks = relationship("Stock", back_populates="product", cascade="all, delete-orphan")


class Stock(Base):
    """ORM Model for Inventory Stock levels."""
    __tablename__ = "stocks"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(String, ForeignKey("products.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=0)
    product = relationship("Product", back_populates="stocks")
'''

ENUMS_PY = '''from enum import Enum

class OrderStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"

    @classmethod
    def next_states(cls, status):
        return {"pending": ["paid"], "paid": []}.get(status, [])
'''

ORDER_PY = '''from sqlalchemy import Column, Integer, String, Float, DateTime
from backend.database import Base

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    total_amount = Column(Float, nullable=False)
    status = Column(String, nullable=False, default="pending")
'''

ROUTER_PY = '''from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.inventory import Product, Stock

router = APIRouter()

@router.get("/")
def list_products(db: Session = Depends(get_db)):
    return db.query(Product).all()
'''


def _files(inventory=V35_INVENTORY, order=ORDER_PY, router=ROUTER_PY):
    return {
        "backend/models/inventory.py": inventory,
        "backend/models/order.py": order,
        "backend/models/enums.py": ENUMS_PY,
        "backend/routers/inventory.py": router,
    }


def test_g1047_v35_product_stock_gets_inventory_class():
    """v35 真实 Product/Stock 双模型形态必须补回 Inventory 类。"""
    files = _files()
    assert dg._g1047_needs_inventory_class(files) is True
    fixed, fixes = dg._repair_missing_inventory_class(files)
    assert fixes, "应产生修复记录"
    assert "Inventory" in dg._base_orm_class_names(fixed["backend/models/inventory.py"])
    # 现有类必须原样保留（保护 R8/R9 已通过的 pytest）
    names = dg._base_orm_class_names(fixed["backend/models/inventory.py"])
    assert "Product" in names and "Stock" in names
    assert fixed["backend/routers/inventory.py"] == files["backend/routers/inventory.py"]


def test_g1047_repaired_contract_extracts_complete():
    """修复后的工作区必须让判卷冻结契约提取 complete=True。"""
    fixed, _ = dg._repair_missing_inventory_class(_files())
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for rel, content in fixed.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        (root / "backend" / "__init__.py").write_text("", encoding="utf-8")
        (root / "backend" / "models" / "__init__.py").write_text("", encoding="utf-8")
        observe = _load_observe_module()
        extracted = observe._extract_model_contract(root)
        assert extracted["complete"] is True, extracted["extraction_errors"]
        assert "Order" in extracted["models"]
        assert "Inventory" in extracted["models"]


def test_g1047_idempotent():
    """已含 Inventory 类时不得重复追加。"""
    fixed, fixes1 = dg._repair_missing_inventory_class(_files())
    assert fixes1
    assert dg._g1047_needs_inventory_class(fixed) is False
    fixed2, fixes2 = dg._repair_missing_inventory_class(fixed)
    assert not fixes2
    assert fixed2 == fixed


def test_g1047_no_inventory_file():
    """inventory.py 缺失时不介入。"""
    files = _files()
    del files["backend/models/inventory.py"]
    assert dg._g1047_needs_inventory_class(files) is False
    fixed, fixes = dg._repair_missing_inventory_class(files)
    assert not fixes and fixed == files


def test_g1047_no_order_model():
    """order.py 无 class Order 时不介入（避免误伤非 ShopFlow 项目）。"""
    files = _files(order="x = 1\n")
    assert dg._g1047_needs_inventory_class(files) is False
    fixed, fixes = dg._repair_missing_inventory_class(files)
    assert not fixes and fixed == files


def test_g1047_existing_inventory_elsewhere():
    """全工作区已有 class Inventory 时不介入（避免重复 ORM 定义）。"""
    files = _files(router=ROUTER_PY + "\nclass Inventory:  # noqa\n    pass\n")
    assert dg._g1047_needs_inventory_class(files) is False
    fixed, fixes = dg._repair_missing_inventory_class(files)
    assert not fixes and fixed == files


def test_g1047_syntax_error_not_touched():
    """追加后语法不合法时不落盘（ast 守卫）。"""
    bad = V35_INVENTORY + "\nclass Broken(:\n"  # 主文件本身已坏
    files = _files(inventory=bad)
    fixed, fixes = dg._repair_missing_inventory_class(files)
    # 主文件坏 → _base_orm_class_names 返回空 → 不触发
    assert not fixes and fixed == files
