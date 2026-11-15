# -*- coding: utf-8 -*-
"""最小修改约束回归契约（v3.7）。

真实故障（2026-11-14 ShopFlow R7）：题面明确写「运行 pytest 报错，只允许修改
包含 bug 的源文件，且只允许最小行数变更」，但模型在 `fix_code` 下仍全量重生成
整套项目 —— run12 改 27 个文件（还新建 backend/core/database.py）、run13 改 19 个，
把「恢复一行 `from typing import List`」做成半重写，引入 201 vs 200、
405 vs 204 等新失败。

修复：把题面契约编译成确定性过滤，只认 traceback `File "xxx.py"` 指向的源文件。
同时严格 FAIL-OPEN：非修复意图、无最小修改措辞、无 traceback 目标、
过滤后为空，一律不生效，避免误伤 R6/R8/R9/R10。
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker.agents.qwen.step_runner import (  # noqa: E402
    _enforce_minimal_fix_scope,
    _extract_traceback_targets,
    _relative_source_path,
)

WS = r"C:\Users\49772\Desktop\shopflow_ecommerce"

R7_REQUEST = """运行 pytest 时出现以下错误，请定位根因并修复所有有问题的文件。
⭐⭐⭐ 禁止操作：只允许修改包含 bug 的源文件，且只允许最小行数变更。
只做最小修改，不要改动测试断言、HTTP 状态码、API 行为。

=== 注入 Bug 后的错误 ===
E   File "C:\\Users\\49772\\Desktop\\shopflow_ecommerce\\backend\\routers\\orders.py", line 3
E       from typing import List
E   NameError: name 'List' is not defined
"""


def _ctx(paths, request=R7_REQUEST, workspace=WS):
    return {
        "meta": {"user_request": request, "workspace_path": workspace},
        "final_file_ops": [
            {"op": "modify", "path": p, "content": "x = 1"} for p in paths
        ],
    }


def test_windows_absolute_traceback_path_is_normalized():
    assert _relative_source_path(
        r"C:\Users\49772\Desktop\shopflow_ecommerce\backend\routers\orders.py", WS
    ) == "backend/routers/orders.py"


def test_traceback_targets_exclude_test_files():
    req = R7_REQUEST + (
        '\nE   File "C:\\Users\\49772\\Desktop\\shopflow_ecommerce\\tests\\conftest.py", line 1\n'
    )
    assert _extract_traceback_targets(req, WS) == ["backend/routers/orders.py"]


def test_minimal_fix_filters_out_unrelated_rewrites():
    ctx = _ctx([
        "backend/routers/orders.py",
        "backend/core/database.py",     # 模型凭空新建
        "backend/models/order.py",
        "backend/schemas/order.py",
        "backend/main.py",
        "tests/conftest.py",
        "docs/readme.md",
    ])
    r = _enforce_minimal_fix_scope(ctx, "fix_code")
    assert r["applied"] is True
    assert [o["path"] for o in ctx["final_file_ops"]] == ["backend/routers/orders.py"]
    assert "backend/core/database.py" in r["dropped"]
    assert "tests/conftest.py" in r["dropped"]


def test_internal_ops_and_init_files_are_preserved():
    ctx = _ctx(["backend/routers/orders.py", "backend/routers/inventory.py"])
    ctx["final_file_ops"].append(
        {"op": "create", "path": "backend/__init__.py", "content": ""})
    ctx["final_file_ops"].append(
        {"op": "create", "path": ".alphapilot_generated.mark", "content": "[]",
         "_internal": True})
    _enforce_minimal_fix_scope(ctx, "fix_code")
    paths = [o["path"] for o in ctx["final_file_ops"]]
    assert "backend/__init__.py" in paths
    assert ".alphapilot_generated.mark" in paths
    assert "backend/routers/inventory.py" not in paths


def test_fail_open_for_non_fix_intents():
    ctx = _ctx(["backend/routers/orders.py", "backend/main.py"])
    assert _enforce_minimal_fix_scope(ctx, "write_code")["applied"] is False
    assert len(ctx["final_file_ops"]) == 2


def test_fail_open_when_no_minimal_change_wording():
    ctx = _ctx(["backend/routers/orders.py", "backend/main.py"],
               request="请帮我重构整个后端，随便改。\n" + R7_REQUEST.split("=== 注入")[1])
    assert _enforce_minimal_fix_scope(ctx, "fix_code")["applied"] is False


def test_fail_open_when_no_traceback_target():
    req = "只允许修改包含 bug 的源文件，且只允许最小行数变更。但没有 traceback。"
    ctx = _ctx(["backend/routers/orders.py", "backend/main.py"], request=req)
    assert _enforce_minimal_fix_scope(ctx, "fix_code")["applied"] is False
    assert len(ctx["final_file_ops"]) == 2


def test_fail_open_when_filter_would_empty_the_delivery():
    ctx = _ctx(["backend/main.py", "docs/readme.md"])
    assert _enforce_minimal_fix_scope(ctx, "fix_code")["applied"] is False
    assert len(ctx["final_file_ops"]) == 2


def test_multiple_traceback_targets_all_kept():
    req = R7_REQUEST + (
        '\nE   File "C:\\Users\\49772\\Desktop\\shopflow_ecommerce\\backend\\models\\order.py", line 9\n'
    )
    ctx = _ctx([
        "backend/routers/orders.py", "backend/models/order.py",
        "backend/main.py", "backend/core/extra.py",
    ], request=req)
    r = _enforce_minimal_fix_scope(ctx, "fix_code")
    assert r["applied"] is True
    assert [o["path"] for o in ctx["final_file_ops"]] == [
        "backend/routers/orders.py", "backend/models/order.py"]


def test_r6_and_r10_prompts_are_not_affected():
    """R6 建项目 / R10 服务层重构不能被最小修改约束误伤。"""
    from python_worker.tests import test_observe_task_system as obs
    for prompt, intent in ((obs.PROMPT_ROUND_6, "write_code"),
                           (obs.PROMPT_ROUND_10, "refactor")):
        ctx = _ctx(["backend/routers/orders.py", "backend/services/order_service.py"],
                   request=prompt)
        assert _enforce_minimal_fix_scope(ctx, intent)["applied"] is False


# ── v3.8 内容级守卫契约 ─────────────────────────────────────────

import pytest

from python_worker.agents.qwen.step_runner import (  # noqa: E402
    _count_diff_lines,
    _enforce_minimal_fix_content,
    _extract_pure_import_additions,
    _is_import_line,
)

OLD_ORDERS = '''"""orders router"""
from fastapi import APIRouter

from backend.models.order import Order
from backend.schemas.order import OrderCreate, OrderResponse

router = APIRouter()

@router.get("/", response_model=list)
def list_orders():
    return [Order(id=1)]
'''

# 模型违约全量重写：恢复了 List 导入，但把 OrderItem 幻觉塞进替换行
REWRITE_HALLUCINATED = '''"""orders router v2 rewrite"""
from typing import List
from fastapi import APIRouter, HTTPException

from backend.models.order import Order, OrderItem
from backend.schemas.order import OrderCreate, OrderResponse, OrderItemResponse

router = APIRouter()

@router.get("/", response_model=List)
def list_orders():
    items = [Order(id=1)]
    return [OrderItem(order=o) for o in items]
'''


def _content_ctx(tmp_path, old, new):
    src = tmp_path / "backend" / "routers" / "orders.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(old, encoding="utf-8")
    ctx = {
        "meta": {"user_request": R7_REQUEST, "workspace_path": str(tmp_path)},
        "final_file_ops": [{"op": "modify", "path": "backend/routers/orders.py",
                             "content": new}],
    }
    scope = {"applied": True, "kept": ["backend/routers/orders.py"], "dropped": []}
    return ctx, scope, src


def test_import_line_detection():
    assert _is_import_line("from typing import List")
    assert _is_import_line("import os")
    assert not _is_import_line("x = fromage(1)")
    assert not _is_import_line("")


def test_huge_rewrite_is_replaced_by_disk_plus_pure_import_additions(tmp_path):
    """run17 复现：全量重写含幻觉导入 → 只保留磁盘现状 + 纯新增 import 行。"""
    ctx, scope, src = _content_ctx(tmp_path, OLD_ORDERS, REWRITE_HALLUCINATED)
    out = _enforce_minimal_fix_content(ctx, scope)
    assert out["blocked_rewrites"] == ["backend/routers/orders.py"]
    content = ctx["final_file_ops"][0]["content"]
    # List 导入被确定性恢复
    assert "from typing import List" in content
    # 幻觉导入与重写的函数体全部被丢弃（外部模块无法验证，保守放行无害）
    assert "OrderItem" not in content
    assert "OrderItemResponse" not in content
    assert "return [Order(id=1)]" in content  # 磁盘原有逻辑保留
    assert "items = [Order(id=1)]" not in content  # 重写体被丢弃
    # 新增 import 落在模块 docstring 之后
    assert content.index('"""orders router"""') < content.index("from typing import List")
    assert "backend/routers/orders.py: from typing import List" in out["import_additions"]


def test_small_diff_passes_through_untouched(tmp_path):
    """真·最小修复（diff ≤ 6 行）原样放行。"""
    minimal = OLD_ORDERS.replace("from fastapi import APIRouter",
                                 "from typing import List\nfrom fastapi import APIRouter")
    ctx, scope, _ = _content_ctx(tmp_path, OLD_ORDERS, minimal)
    out = _enforce_minimal_fix_content(ctx, scope)
    assert out["passed_through"] == ["backend/routers/orders.py"]
    assert not out["blocked_rewrites"]
    assert ctx["final_file_ops"][0]["content"] == minimal


def test_no_import_evidence_fails_open(tmp_path):
    """违约重写但提取不到任何纯新增 import → FAIL-OPEN 放行（不交付空）。"""
    rewrite_no_imports = OLD_ORDERS.replace("def list_orders():", "def list_orders_v2():")
    ctx, scope, _ = _content_ctx(tmp_path, OLD_ORDERS, rewrite_no_imports)
    out = _enforce_minimal_fix_content(ctx, scope)
    assert out["passed_through"] == ["backend/routers/orders.py"]
    assert ctx["final_file_ops"][0]["content"] == rewrite_no_imports


def test_missing_file_and_empty_scope_are_skipped(tmp_path):
    """磁盘上没有旧文件（新建）或 scope 未生效 → 不做内容检查。"""
    ctx = {"meta": {"user_request": R7_REQUEST, "workspace_path": str(tmp_path)},
           "final_file_ops": [{"op": "create", "path": "new_file.py", "content": "x=1"}]}
    out = _enforce_minimal_fix_content(ctx, {"applied": False})
    assert out["checked"] == 0
    out2 = _enforce_minimal_fix_content(ctx, {"applied": True, "kept": ["new_file.py"]})
    assert out2["checked"] == 0  # 磁盘不存在旧文件


def test_extract_returns_all_new_import_lines():
    """提取层 = 行级集合语义：旧内容没有的 import 行全部入选（不受 diff 分块影响）。"""
    old_lines = OLD_ORDERS.splitlines()
    new_lines = REWRITE_HALLUCINATED.splitlines()
    adds = _extract_pure_import_additions(old_lines, new_lines)
    joined = "\n".join(adds)
    assert "from typing import List" in joined
    # 修改过的/新增的 import 行都在候选里，由验证层决定去留
    assert "from backend.models.order import Order, OrderItem" in joined
    assert "from typing import List" not in [l for l in OLD_ORDERS.splitlines()]


def test_diff_count_metric():
    assert _count_diff_lines(["a", "b"], ["a", "b"]) == 0
    assert _count_diff_lines(["a", "b"], ["a", "c"]) == 2
    assert _count_diff_lines(["a"], ["a", "b", "c", "d"]) == 3


def test_validate_kills_hallucinated_internal_imports(tmp_path):
    """验证层：内部模块里不存在的名字（幻觉导入）被确定性丢弃。"""
    from python_worker.agents.qwen.step_runner import _validate_import_additions
    models = tmp_path / "backend" / "models" / "order.py"
    models.parent.mkdir(parents=True, exist_ok=True)
    models.write_text(
        "class Order:\n    pass\n\nclass OrderItem:\n    pass\n",
        encoding="utf-8",
    )
    kept, dropped = _validate_import_additions(str(tmp_path), [
        "from backend.models.order import Order",
        "from backend.models.order import Order, OrderItemResponse",
        "from backend.models.order import Ghost",
        "from typing import List",
    ])
    kept_j = "\n".join(kept)
    assert "from backend.models.order import Order" in kept_j
    assert "from typing import List" in kept_j
    assert "OrderItemResponse" in "\n".join(dropped)
    assert "Ghost" in "\n".join(dropped)


# ── v3.8.1 语法坏行删除契约（run18 实证）────────────────────────
# run18：注入的 Bug 把导入行改成 `from typing import   # ← BUG: List removed`
# —— 语法坏行留在盘上必是 SyntaxError。最小修复 = 加回 List 导入 + 删坏行。

from python_worker.agents.qwen.step_runner import (  # noqa: E402
    _broken_import_lines,
)

OLD_BUGGY = '''from typing import   # ← BUG: List removed
from fastapi import APIRouter, Depends

from backend.models.order import Order

router = APIRouter()


@router.get("/", response_model=list)
def list_orders():
    return [Order(id=1)]
'''

FIX_REWRITE = '''from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.order import Order, OrderItem, Ghost

router = APIRouter()


@router.get("/", response_model=List)
def list_orders(db: Session = Depends(get_db)):
    items = db.query(Order).all()
    return [OrderItem(order=o) for o in items]
'''


def test_broken_import_line_is_detected():
    broken = _broken_import_lines(OLD_BUGGY.splitlines())
    assert len(broken) == 1
    assert "BUG: List removed" in broken[0]
    # 合法完整导入（含别名/行尾注释）不会被误判为坏行
    ok_lines = [
        "from fastapi import APIRouter",
        "import os, sys",
        "from typing import List as L  # noqa",
        "import json  # stdlib",
    ]
    assert _broken_import_lines(ok_lines) == []


def test_minimal_fix_removes_broken_and_restores_import(tmp_path):
    """run18 复现：坏行删除 + List 导入恢复 = 完整的最小修复。"""
    src = tmp_path / "backend" / "routers" / "orders.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(OLD_BUGGY, encoding="utf-8")
    models = tmp_path / "backend" / "models" / "order.py"
    models.parent.mkdir(parents=True, exist_ok=True)
    models.write_text("class Order:/n    pass\n", encoding="utf-8")

    ctx = {
        "meta": {"user_request": R7_REQUEST, "workspace_path": str(tmp_path)},
        "final_file_ops": [{"op": "modify", "path": "backend/routers/orders.py",
                             "content": FIX_REWRITE}],
    }
    out = _enforce_minimal_fix_content(
        ctx, {"applied": True, "kept": ["backend/routers/orders.py"], "dropped": []})
    content = ctx["final_file_ops"][0]["content"]
    # 坏行被删、List 被恢复、原逻辑保留
    assert "BUG: List removed" not in content
    assert "from typing import List" in content
    assert "return [Order(id=1)]" in content
    assert out["blocked_rewrites"] == ["backend/routers/orders.py"]
    assert any("BUG" in d for d in out.get("import_deletions", []))
    # 修复后内容必须能通过语法解析
    import ast
    ast.parse(content)
