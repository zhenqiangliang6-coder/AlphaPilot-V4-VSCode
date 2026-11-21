# python_worker/tests/test_g1046_contracts.py
"""G10.46 冻结「经典 Column(...) 声明」契约的契约测试。

真实故障（shopflow_v27_1，2026-11-16 00:17）：
`1 failed, 6 passed in 1600.72s (0:26:40)` —— R5–R9 五轮四维全绿、
summary 5/5 PASSED，**仅 R10** 挂在判卷前置：

    _build_semantic_contract → _extract_model_contract →
    ContractExtractionError: 真实模型契约提取不完整，禁止生成 PROMPT：
    backend/models/order.py:Order 存在暂不支持的 ORM 声明方式
    （字段: created_at, id, items, status, total_amount, user_id）
    | 未提取到完整模型（Order/Inventory）: ['Inventory']

与 v26（`InventoryItem` 类名违约 → G10.45）不同，v27 的 Inventory 类名
本代已写对、pytest 也全绿；唯一违约是 R6 从零建项目时把
`backend/models/order.py` 写成 SQLAlchemy 2.0 的
`id: Mapped[int] = mapped_column(...)` 风格。题面 PROMPT_ROUND_6 第 113 行
**逐字写死**「Order 模型必须用 SQLAlchemy 经典 Column(...) 写法并继承
Base」，判卷还专门写了 `_looks_like_orm_declaration()` 与 `_parse_orm_class`
的 AnnAssign 分支来检测并 FAIL-CLOSED 拒绝 mapped_column ⇒ 这是「契约明文
+ 判卷明防」的确定性违约（G10.44/45 同族），不是 v23 那种无契约锚点的
随机质量波动。

G10.46 在 build_candidate 之前**就地转写** op content（成长法第 35 条），
把 `Mapped[T] = mapped_column(...)` 确定性转写为语义等价的经典
`Column(...)`，并同步修正 import。R6 from_zero_project 没有合规基线、
R7–R9 的 base 又是上一轮违约落盘，G10.42「恢复基线」模板都不适用。
FAIL-CLOSED：语法错 / 类型无法映射 / 多行或关系型声明 / 转写后仍残留
AnnAssign 或 mapped_column / 已合规 / 非 model 文件 / delete·_internal·
越界·绝对路径·Windows 盘符一律不碰。幂等、不改入参、判卷一字未改。
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
from python_worker.delivery_gate import build_candidate  # noqa: E402


def _load_observe_module():
    """从绝对路径加载判卷模块，断言冻结契约未被放宽（不触发测试收集）。"""
    path = Path(__file__).with_name("test_observe_task_system.py")
    spec = importlib.util.spec_from_file_location("_g1046_observe_contract", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── v27 真实 R6 落盘的 backend/models/order.py（逐字快照）─────────────
V27_ORDER = '''from sqlalchemy import String, Float, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from typing import List, Any
from backend.database import Base
from backend.models.enums import OrderStatus

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, default=OrderStatus.PENDING.value)
    total_amount: Mapped[float] = mapped_column(Float)
    items: Mapped[List[Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
'''

COMPLIANT_ORDER = '''from sqlalchemy import Column, Integer, String, Float, JSON, DateTime
from backend.database import Base

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    name = Column(String)
'''


# ── 1. 纯函数：Mapped/mapped_column → 经典 Column ─────────────────────

def test_downgrade_rewrites_v27_order_to_classic_columns():
    new = dg._g1046_downgrade(V27_ORDER)
    assert new is not None
    assert "Mapped[" not in new and "mapped_column" not in new
    assert "id = Column(Integer, primary_key=True, index=True)" in new
    assert "user_id = Column(String, index=True)" in new
    assert "status = Column(String, default=OrderStatus.PENDING.value)" in new
    assert "total_amount = Column(Float)" in new
    assert "items = Column(JSON, default=list)" in new
    assert "created_at = Column(DateTime, default=datetime.utcnow)" in new
    # import 同步：去掉 Mapped/mapped_column，补 Column + 推出的类型
    assert "from sqlalchemy.orm import Mapped" not in new
    assert "from sqlalchemy import" in new
    sa_line = [l for l in new.splitlines()
               if l.startswith("from sqlalchemy import")][0]
    for t in ("Column", "Integer", "String", "Float", "JSON", "DateTime"):
        assert t in sa_line
    # 其它 import / 字段语义无损
    assert "from datetime import datetime" in new
    assert "from backend.models.enums import OrderStatus" in new


def test_downgrade_result_is_valid_python():
    import ast
    new = dg._g1046_downgrade(V27_ORDER)
    ast.parse(new)  # 不抛


def test_downgrade_idempotent():
    new = dg._g1046_downgrade(V27_ORDER)
    assert dg._g1046_downgrade(new) is None
    assert dg._g1046_downgrade(COMPLIANT_ORDER) is None


def test_downgrade_pure_assign_mapped_column():
    src = '''from sqlalchemy import String
from sqlalchemy.orm import mapped_column
from backend.database import Base

class Order(Base):
    __tablename__ = "orders"
    id = mapped_column(String, primary_key=True)
'''
    new = dg._g1046_downgrade(src)
    assert new is not None
    assert "id = Column(String, primary_key=True)" in new
    assert "mapped_column" not in new


# ── 2. FAIL-CLOSED 边界：不误伤 ───────────────────────────────────────

def test_boundary_compliant_classic_column_not_touched():
    assert dg._g1046_downgrade(COMPLIANT_ORDER) is None


def test_boundary_non_orm_file_not_touched():
    src = '''from sqlalchemy.orm import Mapped
x: Mapped[int] = 1
'''
    assert dg._g1046_downgrade(src) is None


def test_boundary_syntax_error_not_touched():
    assert dg._g1046_downgrade("class Order(Base):\n  : bad = = =\n") is None


def test_boundary_unmappable_type_abstains():
    src = '''from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[CustomThing] = mapped_column(primary_key=True)
'''
    assert dg._g1046_downgrade(src) is None


def test_boundary_multiline_annassign_abstains():
    src = '''from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )
'''
    assert dg._g1046_downgrade(src) is None


def test_boundary_no_column_first_arg_without_annotation_abstains():
    # 纯 Assign 且首参不是已知 SQLA 类型 → 无法确定类型，放弃
    src = '''from sqlalchemy.orm import mapped_column
from backend.database import Base

class Order(Base):
    __tablename__ = "orders"
    id = mapped_column(primary_key=True)
'''
    assert dg._g1046_downgrade(src) is None


def test_boundary_non_string_content():
    assert dg._g1046_downgrade(123) is None
    assert dg._g1046_downgrade(None) is None


# ── 3. 就地改 op（成长法第 35 条）：落盘清单一致 ──────────────────────

def test_restore_rewrites_op_content_in_place():
    ops = [
        {"op": "create", "path": "backend/models/order.py", "content": V27_ORDER},
        {"op": "create", "path": "backend/models/inventory.py", "content": COMPLIANT_ORDER},
    ]
    restored = dg.restore_mapped_column_model_ops(ops)
    assert restored == ["backend/models/order.py"]
    assert ops[0]["content"] == dg._g1046_downgrade(V27_ORDER)
    assert ops[1]["content"] == COMPLIANT_ORDER  # 合规文件不动
    # build_candidate 用改后的 op content → 候选区也是合规的
    cand = build_candidate({}, ops)
    assert cand["backend/models/order.py"] == ops[0]["content"]
    assert "mapped_column" not in cand["backend/models/order.py"]


def test_restore_idempotent():
    ops = [{"op": "create", "path": "backend/models/order.py", "content": V27_ORDER}]
    dg.restore_mapped_column_model_ops(ops)
    once = ops[0]["content"]
    assert dg.restore_mapped_column_model_ops(ops) == []
    assert ops[0]["content"] == once


def test_restore_boundaries_not_touched():
    cases = [
        {"op": "delete", "path": "backend/models/order.py"},
        {"op": "create", "path": "backend/models/order.py", "content": V27_ORDER,
         "_internal": True},
        {"op": "create", "path": "../backend/models/order.py", "content": V27_ORDER},
        {"op": "create", "path": "/abs/backend/models/order.py", "content": V27_ORDER},
        {"op": "create", "path": "C:/backend/models/order.py", "content": V27_ORDER},
        {"op": "create", "path": "backend/routers/orders.py", "content": V27_ORDER},
        {"op": "create", "path": "tests/test_x.py", "content": V27_ORDER},
        {"op": "create", "path": "backend/models/order.txt", "content": V27_ORDER},
    ]
    for op in cases:
        ops = [dict(op)]
        assert dg.restore_mapped_column_model_ops(ops) == [], op.get("path")
        if "content" in op:
            assert ops[0]["content"] == op["content"]


def test_restore_windows_path_normalized():
    ops = [{"op": "create", "path": "backend\\models\\order.py",
            "content": V27_ORDER}]
    assert dg.restore_mapped_column_model_ops(ops) == ["backend/models/order.py"]


# ── 4. 候选区兜底：不改入参、幂等、只碰 model 文件 ────────────────────

def test_repair_candidate_rewrites_and_leaves_input_untouched():
    files = {
        "backend/models/order.py": V27_ORDER,
        "backend/models/inventory.py": COMPLIANT_ORDER,
        "backend/routers/orders.py": V27_ORDER,   # 非 model 目录不动
    }
    out, fixes = dg._repair_mapped_column_models(files)
    assert len(fixes) == 1 and "G10.46" in fixes[0]
    assert "mapped_column" not in out["backend/models/order.py"]
    assert out["backend/models/inventory.py"] == COMPLIANT_ORDER
    assert out["backend/routers/orders.py"] == V27_ORDER  # 非 model 不动
    assert files["backend/models/order.py"] == V27_ORDER  # 入参不变


def test_repair_candidate_idempotent():
    out, _ = dg._repair_mapped_column_models({"backend/models/order.py": V27_ORDER})
    out2, fixes2 = dg._repair_mapped_column_models(out)
    assert fixes2 == []
    assert out2 == out


# ── 5. gate 接入与判卷冻结契约未放宽 ─────────────────────────────────

def test_gate_wires_g1046_into_fixes_and_both_repair_loops():
    src = inspect.getsource(dg.gate)
    assert "restore_mapped_column_model_ops" in src
    assert "orm_fixes" in src
    assert src.count("_repair_mapped_column_models") >= 2  # 主链 + 逐轮重对齐
    assert "orm_candidate_fixes" in src
    # 必须在 build_candidate 之前调用（成长法第 35 条）
    assert src.index("restore_mapped_column_model_ops") < src.index(
        "candidate = build_candidate")


def test_judging_frozen_contract_not_relaxed():
    obs = _load_observe_module()
    src_p = inspect.getsource(obs._parse_orm_class)
    assert "暂不支持的 ORM 声明方式" in src_p
    assert "AnnAssign" in src_p
    src_l = inspect.getsource(obs._looks_like_orm_declaration)
    assert "mapped_column" in src_l
    # 题面仍逐字写死经典 Column 写法
    assert "必须用 SQLAlchemy 经典 Column(...) 写法" in obs.PROMPT_ROUND_6
    # _extract_model_contract 仍要求 Order + Inventory 完整
    src_e = inspect.getsource(obs._extract_model_contract)
    assert '未提取到完整模型（Order/Inventory）' in src_e


# ── 6. 端到端：v27 真实工作区 → 转写 → 判卷契约完整 + 真实 pytest 绿 ──

MINI_DATABASE = '''from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase
engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
class Base(DeclarativeBase):
    pass
'''

MINI_ENUMS = '''from enum import Enum

class OrderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    def next_states(self):
        return []
'''

MINI_INVENTORY = '''from sqlalchemy import Column, Integer, String
from backend.database import Base

class Inventory(Base):
    __tablename__ = "inventory"
    id = Column(Integer, primary_key=True)
    name = Column(String)
'''

MINI_CONFTEST = '''import pytest
from backend.database import Base, engine

@pytest.fixture(autouse=True)
def _tables():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
'''

MINI_TEST = '''from backend.models.order import Order
from backend.models.inventory import Inventory

def test_models():
    assert Order.__tablename__ == "orders"
    assert Inventory.__tablename__ == "inventory"
'''


def _write_project(root: Path, order_src: str):
    files = {
        "backend/__init__.py": "",
        "backend/database.py": MINI_DATABASE,
        "backend/models/__init__.py": "",
        "backend/models/enums.py": MINI_ENUMS,
        "backend/models/inventory.py": MINI_INVENTORY,
        "backend/models/order.py": order_src,
        "tests/conftest.py": MINI_CONFTEST,
        "tests/test_model.py": MINI_TEST,
    }
    for p, s in files.items():
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


def test_end_to_end_v27_contract_complete_and_pytest_green(tmp_path):
    obs = _load_observe_module()
    before_root = tmp_path / "before"
    before_root.mkdir()
    _write_project(before_root, V27_ORDER)
    c0 = obs._extract_model_contract(str(before_root))
    assert c0.get("complete") is False, c0
    assert "Inventory" in c0.get("models", {})
    assert "Order" not in c0.get("models", {})
    assert any("暂不支持的 ORM 声明方式" in e
               for e in c0.get("extraction_errors", [])), c0

    # 就地转写 op → build_candidate → 落盘清单同源合规
    ops = [{"op": "create", "path": "backend/models/order.py",
            "content": V27_ORDER}]
    assert dg.restore_mapped_column_model_ops(ops) == ["backend/models/order.py"]
    fixed_order = ops[0]["content"]

    after_root = tmp_path / "after"
    after_root.mkdir()
    _write_project(after_root, fixed_order)
    c1 = obs._extract_model_contract(str(after_root))
    assert c1.get("complete") is True, c1
    assert "Order" in c1.get("models", {}) and "Inventory" in c1.get("models", {})
    assert c1.get("extraction_errors") == [], c1

    rc, out, err = _run_pytest(after_root)
    assert rc == 0, (rc, out, err)
    assert "1 passed" in out
