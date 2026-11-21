# python_worker/tests/test_g1039_contracts.py
"""G10.39 整段 import 头丢失的确定性重建契约。

真实故障（shopflow_v18_1，2026-11-15 18:21）：主链切到
`deepseek-v4.1-flash` 后速度提升 6 倍（一遍 406s），但 R6 生成的
`backend/schemas/__init__.py` 把 `from ... import (` 头整段丢了，
只剩缩进续行 + 孤立右括号：

    \"\"\"Pydantic schemas package.\"\"\"

        InventoryCreate,
        InventoryDeduct,
        InventoryResponse,
        InventoryUpdate,
    )
    from backend.schemas.order import OrderCreate, ...

G10.24 的 `_repair_broken_syntax` 要求先有一行完整 `from X import Y`
才能合并续行，这里连头都没有 → 修复器不触发 → 闸门以恒定
`ImportError` 判 stalled → 交付 `IndentationError` 文件 → R6 质量红，
R7–R10 全部因「前置条件 pytest 未通过」连锁失败。

契约：孤立续行块里的每个符号，必须在同目录的**唯一**兄弟模块里
找到 AST 顶层真实定义才能重建；无唯一归属一律不修（FAIL-CLOSED，
不臆造模块名）；整体 ast.parse 自检通过才应用；合法文件零改动。
"""

import ast
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker.delivery_gate import (  # noqa: E402
    _repair_orphan_import_block,
    _repair_broken_syntax,
    _top_level_definitions,
)


_SIBLING = '''"""Pydantic schemas for the inventory domain."""

from pydantic import BaseModel


class InventoryCreate(BaseModel):
    sku: str


class InventoryUpdate(BaseModel):
    name: str


class InventoryResponse(BaseModel):
    id: int


class InventoryDeduct(BaseModel):
    quantity: int
'''

_ORDER = '''"""Order schemas."""


class OrderCreate:
    pass


class OrderResponse:
    pass


class OrderUpdateStatus:
    pass
'''

# v18_1 真实损坏形态
_DAMAGED = '''# ============================================================
"""Pydantic schemas package."""

    InventoryCreate,
    InventoryDeduct,
    InventoryResponse,
    InventoryUpdate,
)
from backend.schemas.order import OrderCreate, OrderResponse, OrderUpdateStatus

__all__ = [
    "OrderCreate",
    "OrderResponse",
    "OrderUpdateStatus",
    "InventoryCreate",
    "InventoryUpdate",
    "InventoryResponse",
    "InventoryDeduct",
]
'''


def _files(damaged=_DAMAGED, sibling=_SIBLING, order=_ORDER):
    return {
        "backend/schemas/__init__.py": damaged,
        "backend/schemas/inventory.py": sibling,
        "backend/schemas/order.py": order,
        "backend/main.py": "from backend.schemas import InventoryCreate\n",
    }


def test_damaged_file_is_really_broken():
    with pytest.raises(SyntaxError):
        ast.parse(_DAMAGED)


def test_g1024_repairer_does_not_handle_missing_header():
    """证明这是 G10.24 的覆盖盲区，不是重复造轮子。"""
    out, fixes = _repair_broken_syntax(_files())
    assert fixes == []
    assert out["backend/schemas/__init__.py"] == _DAMAGED


def test_top_level_definitions_only_counts_real_definitions():
    files = _files()
    defs = _top_level_definitions(files, "backend/schemas/inventory.py")
    assert {"InventoryCreate", "InventoryUpdate",
            "InventoryResponse", "InventoryDeduct"} <= defs
    assert "BaseModel" not in defs, "import 进来的名字不算顶层定义"


def test_rebuilds_missing_import_header_from_real_sibling():
    out, fixes = _repair_orphan_import_block(_files())
    fixed = out["backend/schemas/__init__.py"]
    ast.parse(fixed)  # 必须整体可解析
    assert len(fixes) == 1
    assert "重建丢失的 import 头" in fixes[0]
    assert "from backend.schemas.inventory import InventoryCreate" in fixed
    for name in ("InventoryCreate", "InventoryDeduct",
                 "InventoryResponse", "InventoryUpdate"):
        assert name in fixed
    assert ")" not in [ln.strip() for ln in fixed.splitlines() if ln.strip() == ")"]
    assert not [ln for ln in fixed.splitlines()
                if ln.startswith("    ") and ln.strip().rstrip(",").isidentifier()
                and ln.strip().endswith(",")]
    # 原有合法 import 与 __all__ 必须保留
    assert "from backend.schemas.order import OrderCreate" in fixed
    assert "__all__" in fixed
    # 其他文件零改动
    assert out["backend/schemas/inventory.py"] == _SIBLING
    assert out["backend/main.py"] == "from backend.schemas import InventoryCreate\n"


def test_groups_symbols_by_module():
    """符号分属两个兄弟模块时，生成两条 import 而不是臆造一个源。"""
    damaged = '''"""pkg."""\n\n    InventoryCreate,\n    OrderCreate,\n)\n'''
    files = {
        "backend/schemas/__init__.py": damaged,
        "backend/schemas/inventory.py": _SIBLING,
        "backend/schemas/order.py": _ORDER,
    }
    out, fixes = _repair_orphan_import_block(files)
    fixed = out["backend/schemas/__init__.py"]
    ast.parse(fixed)
    assert "from backend.schemas.inventory import InventoryCreate" in fixed
    assert "from backend.schemas.order import OrderCreate" in fixed
    assert len(fixes) == 1


def test_mirror_file_resolves_symbols_from_backend_package():
    """顶层镜像目录的符号定义在 backend/ 对应模块（v18 真实形态）。"""
    damaged = '''"""Compatibility module mirroring backend.schemas.inventory."""\n\n    InventoryCreate,\n    InventoryUpdate,\n)\n'''
    files = {
        "schemas/inventory.py": damaged,
        "schemas/__init__.py": "",
        "backend/schemas/inventory.py": _SIBLING,
        "backend/schemas/__init__.py": "",
    }
    out, fixes = _repair_orphan_import_block(files)
    assert len(fixes) == 1
    fixed = out["schemas/inventory.py"]
    ast.parse(fixed)
    assert "from backend.schemas.inventory import InventoryCreate" in fixed
    assert "InventoryCreate" in fixed and "InventoryUpdate" in fixed


def test_real_v18_workspace_all_orphan_blocks_are_repaired():
    """真实 v18 工作区里 4 个同类损坏必须全部修到 AST 可解析。"""
    files = {
        "backend/schemas/__init__.py": _DAMAGED,
        "backend/schemas/inventory.py": _SIBLING,
        "backend/schemas/order.py": _ORDER,
        "schemas/__init__.py": _DAMAGED.replace("Pydantic schemas package",
                                                "Compatibility package"),
        "schemas/inventory.py": ('"""Compatibility module."""\n\n'
                                 '    InventoryCreate,\n    InventoryUpdate,\n)\n'),
        "routers/inventory.py": ('"""Compatibility module."""\n\n'
                                 '    create_inventory,\n    router,\n)\n'),
        "backend/routers/inventory.py": ('router = "api"\n\n'
                                         'def create_inventory():\n    pass\n'),
    }
    out, fixes = _repair_orphan_import_block(files)
    assert len(fixes) == 4, fixes
    for p, s in out.items():
        ast.parse(s)


def test_same_basename_disambiguates_router_vs_service():
    """router 与 service 都定义同名函数时，优先同名模块，仍要求唯一。"""
    damaged = ('"""Compatibility module."""\n\n'
               '    create_inventory,\n    router,\n)\n')
    files = {
        "routers/inventory.py": damaged,
        "backend/routers/inventory.py": ('router = "api"\n\n'
                                         'def create_inventory():\n    pass\n'),
        "backend/services/inventory_service.py": 'def create_inventory():\n    pass\n',
    }
    out, fixes = _repair_orphan_import_block(files)
    assert len(fixes) == 1, fixes
    fixed = out["routers/inventory.py"]
    ast.parse(fixed)
    assert "from backend.routers.inventory import create_inventory" in fixed


def test_same_basename_ambiguity_still_fail_closed():
    """两个同名模块都定义该符号 → 仍不修。"""
    damaged = ('"""Compatibility module."""\n\n    Shared,\n)\n')
    files = {
        "routers/inventory.py": damaged,
        "backend/routers/inventory.py": 'class Shared:\n    pass\n',
        "backend/services/inventory.py": 'class Shared:\n    pass\n',
    }
    out, fixes = _repair_orphan_import_block(files)
    assert fixes == []
    assert out["routers/inventory.py"] == damaged


def test_unresolved_symbol_is_fail_closed():
    """任一符号无唯一归属 → 整个文件不修，绝不臆造模块名。"""
    damaged = '''"""pkg."""\n\n    InventoryCreate,\n    NotDefinedAnywhere,\n)\n'''
    out, fixes = _repair_orphan_import_block(_files(damaged=damaged))
    assert fixes == []
    assert out["backend/schemas/__init__.py"] == damaged


def test_ambiguous_symbol_is_fail_closed():
    damaged = '''"""pkg."""\n\n    SharedName,\n)\n'''
    dup = '''class SharedName:\n    pass\n'''
    files = {
        "backend/schemas/__init__.py": damaged,
        "backend/schemas/inventory.py": _SIBLING + "\n" + dup,
        "backend/schemas/order.py": _ORDER + "\n" + dup,
    }
    out, fixes = _repair_orphan_import_block(files)
    assert fixes == []
    assert out["backend/schemas/__init__.py"] == damaged


def test_valid_file_untouched():
    valid = '''"""pkg."""\n\nfrom backend.schemas.inventory import InventoryCreate\n\n__all__ = ["InventoryCreate"]\n'''
    files = _files(damaged=valid)
    out, fixes = _repair_orphan_import_block(files)
    assert fixes == []
    assert out["backend/schemas/__init__.py"] == valid


def test_windows_style_paths():
    files = {
        "backend\\schemas\\__init__.py": _DAMAGED,
        "backend\\schemas\\inventory.py": _SIBLING,
        "backend\\schemas\\order.py": _ORDER,
    }
    out, fixes = _repair_orphan_import_block(files)
    assert len(fixes) == 1
    ast.parse(out["backend\\schemas\\__init__.py"])


def test_broken_by_other_reason_is_not_touched():
    """非续行块语法错误（如缺冒号）不归本规则管。"""
    broken = "def f(\n    pass\n"
    files = _files(damaged=broken)
    out, fixes = _repair_orphan_import_block(files)
    assert fixes == []
    assert out["backend/schemas/__init__.py"] == broken
