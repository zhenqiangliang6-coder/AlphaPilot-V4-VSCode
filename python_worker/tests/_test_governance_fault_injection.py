# -*- coding: utf-8 -*-
"""治理机制故障注入测试（G1/G3/G4 + 状态机）。

独立验证统一任务状态机与治理闭环，不依赖 Node.js / Redis：
  1. G1 快照完整性（SHA256 / size / mtime）
  2. SHA256 能识别文件修改
  3. diff 能分类 added/modified/deleted/unchanged
  4. G3 质量门禁拦截测试退化（故障注入）
  5. G4 失败隔离：保留证据 + 回滚基线
  6. 状态机拒绝非法流转

运行方式：
    python -m pytest tests/_test_governance_fault_injection.py -v
"""
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

from test_observe_task_system import (
    TaskState,
    _advance_state,
    _snapshot_workspace,
    _diff_workspace,
    _quality_gate,
    _quarantine_failure,
    _rollback_workspace,
    _build_semantic_contract,
    _extract_model_contract,
    _check_semantic_contract,
    ContractExtractionError,
    SERVICE_LAYER_CONTRACT,
)


# ── 最小项目脚手架 ────────────────────────────────────────────

_SERVICE_SRC = '''# backend/service.py
def add(a, b):
    return a + b
'''

_SERVICE_BROKEN = '''# backend/service.py (injected bug)
def add(a, b):
    return a - b
'''

_TEST_SRC = '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.service import add

def test_add():
    assert add(1, 2) == 3
'''


def _build_project(root: Path, service_content: str = _SERVICE_SRC):
    (root / "backend").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "backend" / "service.py").write_text(service_content, encoding="utf-8")
    (root / "tests" / "test_service.py").write_text(_TEST_SRC, encoding="utf-8")


# ── G1 快照 ───────────────────────────────────────────────────

def test_snapshot_records_sha256_size_mtime():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _build_project(ws)

        snap = _snapshot_workspace(ws)
        assert "backend/service.py" in snap
        entry = snap["backend/service.py"]

        assert "sha256" in entry and len(entry["sha256"]) == 64
        assert entry["size"] > 0
        assert "mtime" in entry
        assert entry["content"].strip().endswith("return a + b")


# ── G1 SHA256 识别修改 ────────────────────────────────────────

def test_sha256_detects_content_modification():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _build_project(ws)
        before = _snapshot_workspace(ws)

        # 故障注入：修改 service.py
        (ws / "backend" / "service.py").write_text(_SERVICE_BROKEN, encoding="utf-8")
        after = _snapshot_workspace(ws)

        assert (
            before["backend/service.py"]["sha256"]
            != after["backend/service.py"]["sha256"]
        ), "SHA256 必须能识别文件被修改"


# ── G3 diff 分类 ──────────────────────────────────────────────

def test_diff_workspace_classifies_changes():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _build_project(ws)
        before = _snapshot_workspace(ws)

        # 修改 + 新增 + 删除
        (ws / "backend" / "service.py").write_text(_SERVICE_BROKEN, encoding="utf-8")
        (ws / "backend" / "new_file.py").write_text("# new", encoding="utf-8")
        (ws / "tests" / "test_service.py").unlink()

        diff = _diff_workspace(ws, before)
        assert "backend/service.py" in diff["modified"]
        assert "backend/new_file.py" in diff["added"]
        assert "tests/test_service.py" in diff["deleted"]
        assert "backend/service.py" not in diff["unchanged"]


# ── G3 质量门禁拦截回归退化 ───────────────────────────────────

def test_quality_gate_blocks_regression():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _build_project(ws)
        snapshot = _snapshot_workspace(ws)

        # 故障注入：破坏代码导致测试失败
        (ws / "backend" / "service.py").write_text(_SERVICE_BROKEN, encoding="utf-8")

        gate = _quality_gate(str(ws), snapshot, contract_checker=None, baseline_test=None)
        assert gate["passed"] is False
        assert gate["checks"]["regression_test"]["passed"] is False
        assert "backend/service.py" in gate["checks"]["file_scope"]["modified"]


def test_quality_gate_passes_clean_workspace():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _build_project(ws)
        snapshot = _snapshot_workspace(ws)

        gate = _quality_gate(str(ws), snapshot, contract_checker=None, baseline_test=None)
        assert gate["passed"] is True
        assert gate["checks"]["regression_test"]["passed"] is True


# ── G4 失败隔离：保留证据 + 回滚基线 ─────────────────────────

def test_quarantine_preserves_diff_and_rolls_back():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _build_project(ws)
        snapshot = _snapshot_workspace(ws)

        # 故障注入
        (ws / "backend" / "service.py").write_text(_SERVICE_BROKEN, encoding="utf-8")
        (ws / "backend" / "junk.py").write_text("# pollute", encoding="utf-8")

        gate = _quality_gate(str(ws), snapshot, contract_checker=None, baseline_test=None)
        assert gate["passed"] is False

        result = _quarantine_failure(str(ws), snapshot, "task-fault-001", gate)

        # 证据保留
        evidence = Path(result["evidence_path"])
        assert evidence.exists()

        # 回滚后基线恢复
        assert (ws / "backend" / "service.py").read_text(encoding="utf-8") == _SERVICE_SRC
        assert not (ws / "backend" / "junk.py").exists()
        assert result["rollback"]["errors"] == []

        # 回滚后回归测试重新通过（基线安全）
        gate_after = _quality_gate(str(ws), snapshot, contract_checker=None, baseline_test=None)
        assert gate_after["passed"] is True


# ── G1/G4 二进制文件防护（回归：.db 不能被文本化损坏）────────

def test_snapshot_rollback_preserves_binary_files():
    """二进制文件（如 SQLite .db）在快照→回滚全程必须 bit-for-bit 一致。

    回归背景：曾用 raw.decode('utf-8', errors='replace') 快照、文本写回，
    导致数据库文件被损坏（sqlite3.DatabaseError: database disk image is malformed）。
    """
    import hashlib
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "backend").mkdir(parents=True, exist_ok=True)
        # 构造含 NUL 字节的二进制内容，模拟 SQLite 数据库
        db_bytes = bytes(range(256)) * 4  # 1024 字节，含 \x00
        (ws / "backend" / "shopflow.db").write_bytes(db_bytes)

        snapshot = _snapshot_workspace(ws)
        entry = snapshot["backend/shopflow.db"]
        assert entry["is_binary"] is True, "含 NUL 字节应被识别为二进制"
        assert entry["content_b64"], "二进制文件必须存 base64 原文"
        assert entry["sha256"] == hashlib.sha256(db_bytes).hexdigest()

        # 故障注入：Worker 破坏了数据库文件
        (ws / "backend" / "shopflow.db").write_bytes(b"corrupted\x00\x00\x00")

        report = _rollback_workspace(ws, snapshot)
        assert report["errors"] == []
        # bit-for-bit 恢复，不允许任何字节丢失
        assert (ws / "backend" / "shopflow.db").read_bytes() == db_bytes


def test_quarantine_binary_evidence_is_not_textualized():
    """隔离现场（failure_evidence）中的二进制文件用 base64 保留，不丢失字节。"""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "backend").mkdir(parents=True, exist_ok=True)
        _build_project(ws)
        db_bytes = bytes(range(256)) * 4
        (ws / "backend" / "shopflow.db").write_bytes(db_bytes)

        snapshot = _snapshot_workspace(ws)

        # 故障注入
        (ws / "backend" / "service.py").write_text(_SERVICE_BROKEN, encoding="utf-8")
        (ws / "backend" / "shopflow.db").write_bytes(b"broken\x00\x00")

        gate = _quality_gate(str(ws), snapshot, contract_checker=None, baseline_test=None)
        assert gate["passed"] is False

        result = _quarantine_failure(str(ws), snapshot, "task-binary-001", gate)
        evidence = Path(result["evidence_path"]).read_text(encoding="utf-8")
        assert '"is_binary": true' in evidence


# ── 状态机 ────────────────────────────────────────────────────

def test_state_machine_rejects_illegal_transition():
    machine = {"state": TaskState.PREPARE, "history": [TaskState.PREPARE]}
    try:
        # PREPARE 不能直接跳到 ACCEPT（必须经过 QUALITY_GATE）
        _advance_state(machine, TaskState.ACCEPT)
        assert False, "应当抛出非法流转异常"
    except RuntimeError as e:
        assert "非法状态流转" in str(e)


def test_state_machine_happy_path():
    machine = {"state": TaskState.PREPARE, "history": [TaskState.PREPARE]}
    for nxt in [
        TaskState.SNAPSHOT,
        TaskState.VERIFY_BASELINE,
        TaskState.WORKER_EXECUTE,
        TaskState.QUALITY_GATE,
        TaskState.ACCEPT,
    ]:
        _advance_state(machine, nxt)
    assert machine["state"] == TaskState.ACCEPT
    assert machine["history"][-1] == TaskState.ACCEPT


def test_state_machine_failure_path():
    machine = {"state": TaskState.PREPARE, "history": [TaskState.PREPARE]}
    for nxt in [
        TaskState.SNAPSHOT,
        TaskState.VERIFY_BASELINE,
        TaskState.WORKER_EXECUTE,
        TaskState.QUALITY_GATE,
        TaskState.QUARANTINE,
        TaskState.PRESERVE_DIFF,
        TaskState.BASELINE_SAFE,
    ]:
        _advance_state(machine, nxt)
    assert machine["state"] == TaskState.BASELINE_SAFE


# ═══════════════════════════════════════════════════════════════
# G10.1 语义契约故障注入（四层门禁：Import / ORM / Router / 调用签名
#       + 枚举契约 + 非目标文件保护）
#
# 基于 ShopFlow 真实 ORM 源码构造的最小后端脚手架：
#   - Order(id/user_id/total_amount/status/items/created_at/updated_at)
#   - Inventory(id/product_name/sku/quantity/unit_price)
#   - OrderStatus 枚举（含 next_states）
# 字段/类型/主键/nullable 均与真实 backend/models/ 一致。
# 验证原则：正向代码不误伤；负向故障（虚构模型/字段/端点/状态码/保护文件）
#           全部被拦截，且契约提取失败时 FAIL-CLOSED。
# ═══════════════════════════════════════════════════════════════

_ORDER_MODEL = '''import uuid
from sqlalchemy import Column, String, Float, DateTime
from sqlalchemy.dialects.sqlite import JSON
from backend.database import Base
from .enums import OrderStatus
from datetime import datetime, timezone


class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False)
    total_amount = Column(Float, nullable=False, default=0.0)
    status = Column(String, nullable=False, default=OrderStatus.PENDING.value)
    items = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
'''

_INVENTORY_MODEL = '''import uuid
from sqlalchemy import Column, String, Integer, Float
from backend.database import Base


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    product_name = Column(String, unique=True, index=True, nullable=False)
    sku = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False, default=0)
    unit_price = Column(Float, nullable=False, default=0.0)
'''

_ENUMS = '''import enum
from typing import List


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    IN_TRANSIT = "in_transit"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    @classmethod
    def next_states(cls, current_status: "OrderStatus") -> List["OrderStatus"]:
        transitions = {
            cls.PENDING: [cls.PROCESSING, cls.CANCELLED],
            cls.PROCESSING: [cls.IN_TRANSIT, cls.CANCELLED],
            cls.IN_TRANSIT: [cls.COMPLETED, cls.CANCELLED],
            cls.COMPLETED: [],
            cls.CANCELLED: [],
        }
        return transitions.get(current_status, [])
'''

_DATABASE = '''from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
'''

_ORDERS_ROUTER = '''from fastapi import APIRouter

router = APIRouter()


@router.post("/", status_code=200)
def create_order():
    pass


@router.get("/", status_code=200)
def list_orders():
    pass


@router.get("/{order_id}", status_code=200)
def get_order(order_id: str):
    pass


@router.put("/{order_id}/status", status_code=200)
def update_order_status(order_id: str):
    pass


@router.delete("/{order_id}", status_code=204)
def delete_order(order_id: str):
    pass
'''

_INVENTORY_ROUTER = '''from fastapi import APIRouter

router = APIRouter()


@router.post("/", status_code=200)
def create_inventory():
    pass


@router.get("/", status_code=200)
def list_inventory():
    pass


@router.get("/{product_name}", status_code=200)
def get_inventory(product_name: str):
    pass


@router.patch("/{product_name}", status_code=200)
def update_inventory(product_name: str):
    pass
'''

_ORDER_SERVICE = '''VALID_TRANSITIONS = {
    "pending": ["processing", "cancelled"],
    "processing": ["in_transit", "cancelled"],
    "in_transit": ["completed", "cancelled"],
    "completed": [],
    "cancelled": [],
}


def get_order(db, order_id):
    pass


def validate_transition(current_status, new_status):
    return new_status in VALID_TRANSITIONS.get(current_status, [])


class OrderService:
    def __init__(self, db):
        self.db = db

    def create_order(self, payload):
        pass

    def get_orders(self):
        pass

    def get_order(self, order_id):
        pass

    def update_status(self, order_id, new_status):
        pass

    def delete_order(self, order_id):
        pass
'''

_INVENTORY_SERVICE = '''class InventoryService:
    def __init__(self, db):
        self.db = db

    def create_inventory(self, payload):
        pass

    def get_inventory_list(self):
        pass

    def get_inventory(self, product_name):
        pass

    def update_inventory(self, product_name, payload):
        pass
'''

_MAIN = '''from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def read_root():
    return {"message": "ShopFlow API is running"}
'''


def _build_shopflow_backend(root: Path):
    """在临时目录构造与 ShopFlow 真实 ORM 源码一致的最小后端脚手架。"""
    (root / "backend" / "models").mkdir(parents=True, exist_ok=True)
    (root / "backend" / "routers").mkdir(parents=True, exist_ok=True)
    (root / "backend" / "services").mkdir(parents=True, exist_ok=True)
    files = {
        "backend/database.py": _DATABASE,
        "backend/models/order.py": _ORDER_MODEL,
        "backend/models/inventory.py": _INVENTORY_MODEL,
        "backend/models/enums.py": _ENUMS,
        "backend/routers/orders.py": _ORDERS_ROUTER,
        "backend/routers/inventory.py": _INVENTORY_ROUTER,
        "backend/services/order_service.py": _ORDER_SERVICE,
        "backend/services/inventory_service.py": _INVENTORY_SERVICE,
        "backend/main.py": _MAIN,
    }
    for rel, content in files.items():
        (root / rel).write_text(content, encoding="utf-8")


# ── 契约提取：来源证据 + 真实语义 ─────────────────────────────

def test_extract_model_contract_has_source_evidence_and_semantics():
    """契约提取必须有来源证据（source_files/source_hashes），
    且 AST 验证真实语义（字段类型/主键/nullable/JSON）而非仅字段名。"""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _build_shopflow_backend(ws)

        extracted = _extract_model_contract(str(ws))
        assert extracted["complete"] is True, extracted["extraction_errors"]
        assert extracted["extraction_errors"] == []
        for rel in (
            "backend/models/order.py",
            "backend/models/inventory.py",
            "backend/models/enums.py",
        ):
            assert rel in extracted["source_files"]
            assert rel in extracted["source_hashes"]
            assert len(extracted["source_hashes"][rel]) == 64

        order = extracted["models"]["Order"]
        assert order["tablename"] == "orders"
        assert order["primary_key_field"] == "id"
        assert order["primary_key_type"] == "String"
        assert order["fields"]["id"]["primary_key"] is True
        assert order["fields"]["user_id"]["nullable"] is False
        assert order["fields"]["items"]["is_json"] is True

        inv = extracted["models"]["Inventory"]
        assert inv["tablename"] == "inventory"
        assert "product_name" in inv["fields"]
        assert "quantity" in inv["fields"]
        assert "unit_price" in inv["fields"]


# ── 正向：真实基线不误伤 ──────────────────────────────────────

def test_semantic_contract_accepts_real_baseline():
    """真实 ShopFlow 基线代码必须完整通过语义契约（含保护文件）。"""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _build_shopflow_backend(ws)
        snapshot = _snapshot_workspace(ws)

        passed, checks = _check_semantic_contract(str(ws), snapshot=snapshot)
        assert passed is True, checks


# ── 负向：导入虚构模型 OrderItem ──────────────────────────────

def test_semantic_contract_blocks_orderitem_import():
    """禁止 import 虚构 ORM 模型 OrderItem。"""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _build_shopflow_backend(ws)
        svc = ws / "backend" / "services" / "order_service.py"
        svc.write_text(
            svc.read_text(encoding="utf-8")
            + "\nfrom backend.models.order import OrderItem\n",
            encoding="utf-8",
        )

        passed, checks = _check_semantic_contract(str(ws))
        assert passed is False
        assert checks["imports"]["passed"] is False
        assert any("OrderItem" in v for v in checks["imports"]["violations"])


# ── 负向：使用禁止字段 customer_name ──────────────────────────

def test_semantic_contract_blocks_forbidden_fields():
    """禁止使用不存在的字段名 customer_name/stock/price。"""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _build_shopflow_backend(ws)
        svc = ws / "backend" / "services" / "inventory_service.py"
        svc.write_text(
            svc.read_text(encoding="utf-8") + "\n_bad = order.customer_name\n",
            encoding="utf-8",
        )

        passed, checks = _check_semantic_contract(str(ws))
        assert passed is False
        assert checks["orm_fields"]["passed"] is False
        assert any("customer_name" in v for v in checks["orm_fields"]["violations"])


# ── 负向：新增 /inventory/list 额外端点 ───────────────────────

def test_semantic_contract_blocks_extra_endpoint():
    """路由端点集合必须与契约一致，额外端点 /inventory/list 应被拦截。"""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _build_shopflow_backend(ws)
        router = ws / "backend" / "routers" / "inventory.py"
        router.write_text(
            router.read_text(encoding="utf-8")
            + '\n\n@router.get("/list", status_code=200)\ndef list_inventory_extra():\n    pass\n',
            encoding="utf-8",
        )

        passed, checks = _check_semantic_contract(str(ws))
        assert passed is False
        assert checks["router_contract"]["passed"] is False
        assert any("额外端点" in v for v in checks["router_contract"]["violations"])


# ── 负向：POST /orders/ 返回 201 ──────────────────────────────

def test_semantic_contract_blocks_201_status():
    """路由响应状态码漂移（POST /orders/ 从 200 改为 201）应被拦截。"""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _build_shopflow_backend(ws)
        router = ws / "backend" / "routers" / "orders.py"
        content = router.read_text(encoding="utf-8")
        assert '@router.post("/", status_code=200)' in content
        router.write_text(
            content.replace(
                '@router.post("/", status_code=200)',
                '@router.post("/", status_code=201)',
            ),
            encoding="utf-8",
        )

        passed, checks = _check_semantic_contract(str(ws))
        assert passed is False
        assert checks["router_contract"]["passed"] is False
        assert any("状态码" in v for v in checks["router_contract"]["violations"])


# ── 负向：修改受保护文件 main.py ─────────────────────────────

def test_semantic_contract_blocks_protected_file_modification():
    """非目标文件 main.py 的内容级保护：整文件哈希不一致应被拦截。"""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _build_shopflow_backend(ws)
        snapshot = _snapshot_workspace(ws)

        (ws / "backend" / "main.py").write_text("# hacked\n", encoding="utf-8")

        passed, checks = _check_semantic_contract(str(ws), snapshot=snapshot)
        assert passed is False
        assert checks["protected_files"]["passed"] is False
        assert any(
            "受保护文件被修改" in v for v in checks["protected_files"]["violations"]
        )


# ── FAIL-CLOSED：模型提取不完整必须中止 ───────────────────────

def test_build_semantic_contract_fail_closed_on_missing_model():
    """模型契约提取不完整时必须 FAIL-CLOSED，绝不回退为空契约放行。"""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        _build_shopflow_backend(ws)
        (ws / "backend" / "models" / "inventory.py").unlink()

        with pytest.raises(ContractExtractionError):
            _build_semantic_contract(str(ws))