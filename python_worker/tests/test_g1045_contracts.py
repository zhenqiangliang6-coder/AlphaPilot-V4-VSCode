# python_worker/tests/test_g1045_contracts.py
"""G10.45 判卷 R10 冻结模型契约客观状态兜底的契约测试。

真实故障（shopflow_v26_1，2026-11-15 23:07）：
`1 failed, 6 passed in 1434.08s (0:23:54)` —— R5–R9 五轮四维全绿、
summary 5/5 PASSED，**仅 R10** 挂在判卷侧：

    _build_semantic_contract → _extract_model_contract →
    ContractExtractionError: 真实模型契约提取不完整，禁止生成 PROMPT：
    未提取到完整模型（Order/Inventory）: ['InventoryItem', 'Order']

工作区 `backend/models/inventory.py` 是
`class InventoryItem(Base): __tablename__ = "inventory_items"`，而 R8 题面
第 205/209 行写死 `Inventory` / `__tablename__ = "inventory"` /
`from backend.models.inventory import Inventory`；判卷 R10 的冻结契约
（模型集合必须含 Order + Inventory）是**全局**的，不随轮次题面变。

G10.32 `_repair_explicit_structure_contract` 逻辑本身正确（对 v26 工作区
+ R8 题面实证能产出 `InventoryItem → Inventory / 表 inventory` 修复，
修复后 `_extract_model_contract` complete=True 且 pytest 7 passed），
但它只在 `user_request` 含「Inventory 模型必须」的 R8 题面触发；
`InventoryItem` 留到 R9（枚举替换题面不含该 marker）之后，R9/R10 的
gate 不再对齐 ⇒ 判卷 FAIL-CLOSED 正确拒绝（不是判卷 bug）。

G10.45 加一层不依赖 user_request 的客观状态兜底：候选工作区里
`backend/models/inventory.py` 的 Base 子类恰好 1 个且非 Inventory、
全工作区没有 `class Inventory`、且 `backend/models/order.py` 有
`class Order` 时，复用 G10.32 已验证的全文替换逻辑对齐类名/表名。
FAIL-CLOSED、幂等、不改判卷。
"""

import importlib.util
import inspect
import os
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import python_worker.delivery_gate as dg  # noqa: E402


def _load_observe_module():
    """从绝对路径加载判卷模块，断言冻结契约未被放宽（不触发测试收集）。"""
    path = Path(__file__).with_name("test_observe_task_system.py")
    spec = importlib.util.spec_from_file_location("_g1045_observe_contract", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── v26 真实 R9/R10 工作区模型文件（逐字快照）───────────────────────
BAD_INVENTORY = '''from sqlalchemy import Column, Integer, String
from backend.database import Base

class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    quantity = Column(Integer, default=0, nullable=False)
'''

BAD_ORDER = '''from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from backend.database import Base

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    status = Column(String, default="pending", nullable=False)
'''

BAD_INIT = '''from backend.models.order import Order
from backend.models.inventory import InventoryItem
'''

BAD_ROUTER = '''from backend.models.inventory import InventoryItem

def probe():
    return InventoryItem
'''


def _files():
    return {
        "backend/__init__.py": "",
        "backend/database.py": "from sqlalchemy.orm import DeclarativeBase\nclass Base(DeclarativeBase):\n    pass\n",
        "backend/models/__init__.py": "",
        "backend/models/order.py": BAD_ORDER,
        "backend/models/inventory.py": BAD_INVENTORY,
        "backend/routers/inventory.py": BAD_ROUTER,
    }


# ── 1. 客观状态违约判定 ──────────────────────────────────────────────

def test_detects_v26_frozen_contract_violation():
    files = _files()
    files["backend/models/__init__.py"] = BAD_INIT
    assert dg._g1045_model_contract_violated(files) is True


def test_boundary_already_compliant():
    files = _files()
    files["backend/models/inventory.py"] = (
        'from backend.database import Base\n'
        'class Inventory(Base):\n    __tablename__ = "inventory"\n')
    assert dg._g1045_model_contract_violated(files) is False


def test_boundary_existing_class_inventory_elsewhere():
    files = _files()
    files["backend/other.py"] = "class Inventory:\n    pass\n"
    assert dg._g1045_model_contract_violated(files) is False


def test_boundary_missing_order_file_or_class():
    files = _files()
    del files["backend/models/order.py"]
    assert dg._g1045_model_contract_violated(files) is False
    files = _files()
    files["backend/models/order.py"] = "class NotOrder(Base):\n    pass\n"
    assert dg._g1045_model_contract_violated(files) is False


def test_boundary_multiple_orm_classes():
    files = _files()
    files["backend/models/inventory.py"] = (
        "class A(Base):\n    pass\nclass B(Base):\n    pass\n")
    assert dg._g1045_model_contract_violated(files) is False


def test_boundary_non_target_project():
    assert dg._g1045_model_contract_violated({}) is False
    assert dg._g1045_model_contract_violated(
        {"backend/models/inventory.py": BAD_INVENTORY}) is False


# ── 2. 修复：类名 / 表名 / 全部引用 ──────────────────────────────────

def test_repair_renames_class_tablename_and_all_references():
    files = _files()
    files["backend/models/__init__.py"] = BAD_INIT
    out, fixes = dg._repair_frozen_model_contract(files)
    assert len(fixes) == 1
    assert "InventoryItem → Inventory" in fixes[0]
    inv = out["backend/models/inventory.py"]
    assert "class Inventory(Base):" in inv
    assert '__tablename__ = "inventory"' in inv
    assert "InventoryItem" not in inv
    # 全文替换：__init__ 与 router 的 import / 引用一并对齐
    assert "from backend.models.inventory import Inventory" in out[
        "backend/models/__init__.py"]
    assert "InventoryItem" not in out["backend/models/__init__.py"]
    assert "from backend.models.inventory import Inventory" in out[
        "backend/routers/inventory.py"]
    assert "InventoryItem" not in out["backend/routers/inventory.py"]
    # 未违约文件一字不动
    assert out["backend/models/order.py"] == BAD_ORDER


def test_repair_idempotent_and_input_untouched():
    files = _files()
    files["backend/models/__init__.py"] = BAD_INIT
    out, fixes = dg._repair_frozen_model_contract(files)
    assert fixes
    assert files["backend/models/inventory.py"] == BAD_INVENTORY  # 不改入参
    out2, fixes2 = dg._repair_frozen_model_contract(out)
    assert fixes2 == []
    assert out2 == out


def test_compliant_files_never_touched():
    files = _files()
    files["backend/models/inventory.py"] = (
        'from backend.database import Base\n'
        'class Inventory(Base):\n    __tablename__ = "inventory"\n')
    out, fixes = dg._repair_frozen_model_contract(files)
    assert fixes == []
    assert out == files


# ── 3. gate 接入与判卷冻结契约未放宽 ─────────────────────────────────

def test_gate_wires_g1045_into_fixes_and_repair_loop():
    src = inspect.getsource(dg.gate)
    assert "_repair_frozen_model_contract" in src
    assert "model_fixes" in src
    assert src.count("_repair_frozen_model_contract") >= 2  # 主链 + 逐轮重对齐


def test_judging_frozen_contract_not_relaxed():
    obs = _load_observe_module()
    src = inspect.getsource(obs._extract_model_contract)
    assert '未提取到完整模型（Order/Inventory）' in src
    # 判卷 R8 题面仍写死 Inventory 类名 / 表名 / import 链
    p = obs.PROMPT_ROUND_8
    assert '__tablename__ = "inventory"' in p
    assert "from backend.models.inventory import Inventory" in p
    # SERVICE_LAYER_CONTRACT 禁止模型仍冻结
    assert "OrderItem" in obs.SERVICE_LAYER_CONTRACT["forbidden_imports"]


# ── 4. 端到端：自包含最小项目 + 真实 pytest + 判卷契约提取 ───────────

MINI_DATABASE = '''from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase
engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
class Base(DeclarativeBase):
    pass
'''

MINI_CONFTEST = '''import pytest
from backend.database import Base, engine

@pytest.fixture(autouse=True)
def _tables():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
'''

# 判卷 _extract_model_contract() 要求 order.py / inventory.py / enums.py 三文件齐全，
# 缺任一即 complete=False（见 test_observe_task_system.py:484-505）。真实工作区有
# enums.py；v26 首版最小项目漏了它，导致 before/after 都恒为 complete=False。
# 这里补齐一个与真实工作区同构的枚举文件，保持 before/after 唯一差异是 G10.45 修复。
MINI_ENUMS = '''from enum import Enum

class OrderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    def next_states(self):
        return []
'''

MINI_TEST_BAD = '''from backend.models import InventoryItem

def test_model():
    assert InventoryItem is not None
'''

MINI_TEST_OK = '''from backend.models import Inventory

def test_model():
    assert Inventory is not None
    assert Inventory.__tablename__ == "inventory"
'''


def _write_project(root: Path, files: dict, extra: dict | None = None):
    for p, s in {**files, **(extra or {})}.items():
        fp = root / p
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(s, encoding="utf-8")


def _run_pytest(root: Path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--disable-warnings"],
        cwd=str(root), env=env, capture_output=True, text=True, timeout=180,
    )
    return r.returncode, r.stdout, r.stderr


def test_end_to_end_pytest_green_and_contract_complete(tmp_path):
    obs = _load_observe_module()
    files = _files()
    files["backend/models/__init__.py"] = BAD_INIT
    files["backend/database.py"] = MINI_DATABASE

    # 真实工作区三模型文件齐全（含 enums.py）。common 部分 before/after 完全一致，
    # 只有测试文件按修复前/后各自的模型名命名，确保 before 仅做契约提取（不跑 pytest），
    # after 既做契约提取也跑真实 pytest，验证「修复后契约完整且无回归」。
    common = {
        "backend/models/enums.py": MINI_ENUMS,
        "tests/conftest.py": MINI_CONFTEST,
    }
    before_extra = {**common, "tests/test_model.py": MINI_TEST_BAD}
    after_extra = {**common, "tests/test_model.py": MINI_TEST_OK}

    before_root = tmp_path / "before"
    before_root.mkdir()
    _write_project(before_root, files, before_extra)
    c0 = obs._extract_model_contract(str(before_root))
    assert c0.get("complete") is False, c0
    assert "InventoryItem" in c0.get("models", {}), c0
    assert "Inventory" not in c0.get("models", {}), c0
    # 三文件必须齐全，否则「模型文件缺失」也会让 complete=False，掩盖真实违约根因
    assert not any("模型文件缺失" in e for e in c0.get("extraction_errors", [])), c0

    repaired, fixes = dg._repair_frozen_model_contract(files)
    assert fixes
    after_root = tmp_path / "after"
    after_root.mkdir()
    _write_project(after_root, repaired, after_extra)
    c1 = obs._extract_model_contract(str(after_root))
    assert c1.get("complete") is True, c1
    assert "Inventory" in c1.get("models", {}), c1
    assert "InventoryItem" not in c1.get("models", {}), c1

    rc, out, err = _run_pytest(after_root)
    assert rc == 0, (rc, out, err)
    assert "1 passed" in out
