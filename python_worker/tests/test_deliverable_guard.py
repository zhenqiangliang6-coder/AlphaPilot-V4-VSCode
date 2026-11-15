# -*- coding: utf-8 -*-
"""交付完整性守卫回归契约。

锁死两类真实故障：
  1. 多文件生成漏掉用户点名的文件（例如只写实现、漏掉测试文件）；
  2. 分批生成时同一文件产出两套路径（backend/models/order.py 与 models/order.py），
     错位文件污染工作区根目录，甚至被 pytest 收集后炸掉整轮测试。
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker.agents.qwen.step_runner import (  # noqa: E402
    _extract_requested_paths,
    _reconcile_misplaced_paths,
)


def test_extract_ignores_negative_sentences():
    req = (
        "1. backend/models/order.py\n"
        "2. tests/test_orders.py\n"
        "禁止创建扁平的 backend/models.py 或 backend/schemas.py 单文件\n"
        "不要修改 tests/test_orders.py 里已有的断言\n"
    )
    paths = _extract_requested_paths(req)
    assert "backend/models/order.py" in paths
    assert "tests/test_orders.py" in paths
    assert "backend/models.py" not in paths
    assert "backend/schemas.py" not in paths


def test_extract_keeps_path_when_negative_word_comes_after_it():
    """否定词出现在路径之后时，路径仍是交付目标（旧版整行过滤会误杀）。"""
    req = (
        "3. 修改 backend/routers/orders.py —— 路由只负责解析参数，不得包含任何数据库查询\n"
        "4. 修改 backend/routers/inventory.py —— 禁止新增列表专用端点\n"
    )
    assert _extract_requested_paths(req) == [
        "backend/routers/orders.py", "backend/routers/inventory.py"
    ]


def test_negative_scope_stops_at_clause_boundary():
    """否定词不跨分句污染后面的正向交付目标。"""
    req = (
        "禁止新增 backend/extra.py；同时请创建 backend/services/order_service.py\n"
        "不要改动 tests/old_test.py。请生成 tests/new_test.py\n"
    )
    paths = _extract_requested_paths(req)
    assert "backend/extra.py" not in paths
    assert "tests/old_test.py" not in paths
    assert "backend/services/order_service.py" in paths
    assert "tests/new_test.py" in paths


def test_extract_ignores_api_paths_and_imports():
    req = (
        "POST /orders/{order_id}/status 返回 200\n"
        "from backend.models.order import Order, OrderItem\n"
        "生成 backend/routers/orders.py 和 docs/design.md\n"
    )
    assert _extract_requested_paths(req) == [
        "backend/routers/orders.py", "docs/design.md"
    ]


def test_misplaced_duplicate_is_dropped_when_correct_exists():
    expected = ["backend/models/order.py", "backend/models/enums.py"]
    ops = [
        {"path": "backend/models/order.py", "content": "class Order: pass"},
        {"path": "models/order.py", "content": "duplicated"},
        {"path": "tests/test_orders.py", "content": "def test_x(): pass"},
    ]
    dropped, renamed = _reconcile_misplaced_paths(ops, expected)

    assert dropped == ["models/order.py"]
    assert renamed == []
    assert ops[1].get("_drop") is True
    assert ops[2]["path"] == "tests/test_orders.py"  # 非目标文件不动


def test_misplaced_only_version_is_renamed_to_authoritative_path():
    expected = ["backend/models/enums.py", "tests/test_orders.py"]
    ops = [
        {"path": "models/enums.py", "content": "class OrderStatus: pass"},
        {"path": "test_orders.py", "content": "def test_x(): pass"},
    ]
    dropped, renamed = _reconcile_misplaced_paths(ops, expected)

    assert dropped == []
    assert ops[0]["path"] == "backend/models/enums.py"
    assert ops[1]["path"] == "tests/test_orders.py"
    assert ("models/enums.py", "backend/models/enums.py") in renamed


def test_reconcile_is_noop_when_all_paths_correct():
    expected = ["backend/main.py", "tests/test_orders.py"]
    ops = [{"path": p, "content": "x"} for p in expected]
    dropped, renamed = _reconcile_misplaced_paths(ops, expected)
    assert (dropped, renamed) == ([], [])
