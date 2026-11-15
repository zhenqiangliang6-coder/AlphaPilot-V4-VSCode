# python_worker/tests/test_round8_intent_guard.py
"""R8 意图误分类回归契约（G10.13）。

真实故障（shopflow_full_run1）：R8 题面「给 ShopFlow 增加『库存管理』模块 …
否则 pytest 会报 no such table」命中 `_TEST_EXECUTION_PATTERNS` 里的裸
`pytest\\b`，而 `_is_project_test_request()` 的显式修改豁免词表漏了
「增加」这个动词，于是整轮被短路成 `run_tests`（只读链 analyze→plan→test，
无 write 步骤），库存模块从未生成。R8 质量门又只看 pytest 结果，
假阳性判绿；直到 R10 的 FAIL-CLOSED 语义契约提取（要求 Inventory 模型）
才暴露。
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker.intent_router._router import IntentRouter  # noqa: E402

R8_PROMPT_HEAD = """给 ShopFlow 电商系统增加「库存管理」模块。仔细阅读已有代码后再动手，不要破坏现有功能。

新增内容：
1. backend/models/inventory.py
   - Inventory 模型必须用 SQLAlchemy 经典 Column(...) 写法并继承 Base
   - 必须在 backend/models/__init__.py 追加导入，
     否则 Base.metadata 里没有 inventory 表，pytest 会报 "no such table: inventory"

2. backend/schemas/inventory.py — InventoryCreate, InventoryUpdate, InventoryResponse
3. backend/routers/inventory.py — REST API
"""

R10_PROMPT_HEAD = """重构 ShopFlow 后端：把路由中的业务逻辑提取到服务层。
请先阅读 backend/routers/、backend/models/、backend/schemas/ 与 tests/ 下的现有代码，
重构完成后 pytest 必须全部通过。

1. backend/services/order_service.py — OrderService
2. backend/routers/orders.py — 只做参数校验与响应
"""


def test_r8_increment_request_is_not_run_tests():
    assert IntentRouter._is_test_execution_request(R8_PROMPT_HEAD)
    assert not IntentRouter._is_project_test_request(R8_PROMPT_HEAD), (
        "R8 增量功能题面不能被 pytest 字样短路成 run_tests"
    )


def test_r10_refactor_request_is_not_run_tests():
    assert IntentRouter._is_test_execution_request(R10_PROMPT_HEAD)
    assert not IntentRouter._is_project_test_request(R10_PROMPT_HEAD)


def test_pure_test_requests_still_route_to_run_tests():
    for prompt in ("请运行 pytest 检查当前项目", "运行测试", "run pytest",
                   "帮我执行一下单元测试", "python -m pytest"):
        assert IntentRouter._is_project_test_request(prompt), prompt


def test_bare_add_verb_is_recognized_as_explicit_change():
    """「增加…模块」这种最朴素的增量措辞也必须命中豁免（旧词表漏了「增加」）。"""
    p = "给系统增加库存管理模块，pytest 会校验结果"
    assert IntentRouter._is_test_execution_request(p)
    assert not IntentRouter._is_project_test_request(p)


def test_r8_quality_gate_includes_file_existence():
    """防回退：R8 质量门必须把 inv_* 三文件存在性纳入 quality_ok。"""
    src = (_PROJECT_ROOT / "python_worker" / "tests"
           / "test_observe_task_system.py").read_text(encoding="utf-8")
    seg = src.split("def test_round8_incremental_feature")[1][:6000]
    assert "quality_ok = bool(" in seg
    assert "inv_model and inv_router and inv_test" in seg
