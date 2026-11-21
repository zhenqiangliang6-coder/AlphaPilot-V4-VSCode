# python_worker/tests/test_g1041_contracts.py
"""G10.41 空壳化结构完整性守卫契约。

真实故障（shopflow_v20_1，2026-11-15 19:04–19:15）：
`1 failed, 6 passed in 641.80s`，R5–R9 **五轮四维全绿**，R10 抛
`ContractExtractionError: 未提取到完整模型（Order/Inventory）: ['Order']`。

取证（Redis `task_result` 的 final_file_ops）：
- R8 `695d98b5`：`backend/models/inventory.py` 467 字符，含
  `class Inventory(Base)` 与经典 `Column(...)` 写法；`tests/test_inventory.py`
  4336 字符 —— **R8 产物是正确的**。
- R9 `87b5908a`（题面只是「枚举值级联替换」）：把 inventory 的
  5 个文件全部重写成一行 docstring：`backend/models/inventory.py`
  32 字符、`tests/test_inventory.py` 33 字符、`schemas/inventory.py`
  33 字符、`routers/inventory.py` 27 字符、`models/__init__.py` 39 字符。

实现与测试**一起消失** ⇒ 候选区 pytest 依然全绿（其余 test_orders.py
不依赖 Inventory，G10.37 的 exit 5 守卫也不触发）⇒ 闸门所有基于
失败数的 worsening / stalled 判定完全无信号 ⇒ R9 四维判绿；
缺陷潜伏到 R10 提取真实模型契约时才 FAIL-CLOSED 暴露。

契约：完整性守卫必须**不依赖 pytest 失败信号**；就地修正
final_file_ops，保证候选区与落盘清单一致；只恢复基线里已存在且
原本非空的 .py，不碰 delete / 新建 / 语法错误文件。
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker.delivery_gate import (  # noqa: E402
    build_candidate,
    is_hollow_python,
    restore_hollowed_ops,
)


_INVENTORY_MODEL = '''"""Inventory database models."""
from sqlalchemy import Column, String, Integer, Float
from backend.database import Base


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(String(36), primary_key=True)
    product_name = Column(String(200), nullable=False, unique=True)
    sku = Column(String(64), nullable=False)
    quantity = Column(Integer, nullable=False, default=0)
    unit_price = Column(Float, nullable=False, default=0.0)
'''

_INVENTORY_TEST = '''"""Inventory endpoint tests."""
from fastapi.testclient import TestClient
from backend.main import app


def test_inventory_crud():
    client = TestClient(app)
    assert client.get("/inventory").status_code == 200
'''

_ORDERS_TEST = '''"""Order endpoint tests."""


def test_smoke():
    assert 1 + 1 == 2
'''


def _base():
    return {
        "backend/models/inventory.py": _INVENTORY_MODEL,
        "tests/test_inventory.py": _INVENTORY_TEST,
        "tests/test_orders.py": _ORDERS_TEST,
        "backend/models/__init__.py": "from backend.models.inventory import Inventory\n",
    }


def _r9_ops():
    """v20 R9 真实形态：清理 delete + 5 个 docstring-only 的 create。"""
    return [
        {"op": "delete", "path": "backend/models/inventory.py"},
        {"op": "create", "path": "backend/models/inventory.py",
         "content": '"""Inventory database models."""'},
        {"op": "create", "path": "tests/test_inventory.py",
         "content": '"""Tests for inventory routes."""'},
        {"op": "create", "path": "tests/test_orders.py",
         "content": '"""Tests for order routes."""'},
        {"op": "create", "path": "backend/models/__init__.py",
         "content": '"""Database models and enumerations."""'},
    ]


# ---------------------------------------------------------------- 空壳判定

def test_hollow_python_shapes():
    assert is_hollow_python('"""docstring only."""')
    assert is_hollow_python('"""doc."""\n\n# a comment\n')
    assert is_hollow_python('')
    assert is_hollow_python('# just a comment\n')
    assert not is_hollow_python(_INVENTORY_MODEL)
    assert not is_hollow_python('import os\n')
    assert not is_hollow_python('x = 1\n')
    assert not is_hollow_python('def f():\n    pass\n')
    # 语法错误交给别的修复器，本守卫不猜
    assert not is_hollow_python('    Orphan,\n)\n')
    assert not is_hollow_python(None)


# ---------------------------------------------------------------- 恢复规则

def test_restores_all_hollowed_existing_files():
    ops = _r9_ops()
    base = _base()
    restored = restore_hollowed_ops(ops, base)
    assert set(restored) == {
        "backend/models/inventory.py",
        "tests/test_inventory.py",
        "tests/test_orders.py",
        "backend/models/__init__.py",
    }
    cand = build_candidate(base, ops)
    assert "class Inventory(Base)" in cand["backend/models/inventory.py"]
    assert "def test_inventory_crud" in cand["tests/test_inventory.py"]
    assert "def test_smoke" in cand["tests/test_orders.py"]
    assert "from backend.models.inventory import Inventory" in cand["backend/models/__init__.py"]


def test_in_place_edit_keeps_delivery_manifest_consistent():
    """必须就地改 op：候选区恢复而落盘清单仍是空壳属于半成品修复。"""
    ops = [{"op": "create", "path": "backend/models/inventory.py",
            "content": '"""Inventory database models."""'}]
    restore_hollowed_ops(ops, _base())
    assert "class Inventory(Base)" in ops[0]["content"]


def test_does_not_touch_delete_or_internal_ops():
    ops = [
        {"op": "delete", "path": "backend/models/inventory.py",
         "content": '"""Inventory database models."""'},
        {"op": "create", "path": "backend/models/inventory.py",
         "content": '"""Inventory database models."""', "_internal": True},
    ]
    assert restore_hollowed_ops(ops, _base()) == []
    assert ops[0]["content"] == '"""Inventory database models."""'
    assert ops[1]["content"] == '"""Inventory database models."""'


def test_does_not_restore_when_baseline_is_itself_hollow():
    base = {"backend/models/inventory.py": '"""placeholder"""'}
    ops = [{"op": "create", "path": "backend/models/inventory.py",
            "content": '"""Inventory database models."""'}]
    assert restore_hollowed_ops(ops, base) == []


def test_does_not_restore_new_files():
    ops = [{"op": "create", "path": "backend/models/new_model.py",
            "content": '"""New module."""'}]
    assert restore_hollowed_ops(ops, _base()) == []


def test_does_not_restore_when_content_has_real_code():
    ops = [{"op": "create", "path": "backend/models/inventory.py",
            "content": '"""doc."""\n\nclass Inventory(Base):\n    pass\n'}]
    assert restore_hollowed_ops(ops, _base()) == []


def test_does_not_restore_syntax_error_shell():
    ops = [{"op": "create", "path": "backend/models/inventory.py",
            "content": '    InventoryCreate,\n)\n'}]
    assert restore_hollowed_ops(ops, _base()) == []


def test_windows_style_paths_are_normalized():
    ops = [{"op": "create", "path": "backend\\models\\inventory.py",
            "content": '"""Inventory database models."""'}]
    restored = restore_hollowed_ops(ops, _base())
    assert restored == ["backend/models/inventory.py"]
    assert "class Inventory(Base)" in ops[0]["content"]


def test_path_traversal_is_ignored():
    ops = [{"op": "create", "path": "../backend/models/inventory.py",
            "content": '"""doc."""'}]
    assert restore_hollowed_ops(ops, _base()) == []


# ---------------------------------------------------------------- 端到端伪通过

def test_green_pytest_with_hollowed_files_still_gets_structural_repair():
    """核心回归：实现+测试一起被删时 pytest 仍全绿，失败数无信号。"""
    from python_worker.delivery_gate import _run_pytest
    # 自洽的迷你工作区：测试不 import backend，清空实现不影响收集
    base = {
        "backend/models/inventory.py": (
            '"""Inventory database models."""\n\nclass Inventory:\n'
            '    __tablename__ = "inventory"\n'),
        "tests/test_inventory.py": (
            '"""Inventory endpoint tests."""\n\n'
            'def test_inventory_crud():\n    assert True\n'),
        "tests/test_orders.py": (
            '"""Order endpoint tests."""\n\ndef test_smoke():\n    assert True\n'),
    }
    ops = [
        {"op": "create", "path": "backend/models/inventory.py",
         "content": '"""Inventory database models."""'},
        {"op": "create", "path": "tests/test_inventory.py",
         "content": '"""Tests for inventory routes."""'},
    ]
    hollow = build_candidate(base, ops)
    ok_hollow, _ = _run_pytest(hollow)
    assert ok_hollow is True, "还原故障前提：实现被删时 pytest 依然通过"
    assert "class Inventory" not in hollow["backend/models/inventory.py"]

    # 结构守卫不依赖失败数，仍必须恢复
    restored = restore_hollowed_ops(ops, base)
    assert set(restored) == {"backend/models/inventory.py",
                             "tests/test_inventory.py"}
    fixed = build_candidate(base, ops)
    assert "class Inventory" in fixed["backend/models/inventory.py"]
    assert "def test_inventory_crud" in fixed["tests/test_inventory.py"]
    ok_fixed, _ = _run_pytest(fixed)
    assert ok_fixed is True
