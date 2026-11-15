# -*- coding: utf-8 -*-
"""ShopFlow 题面自洽性回归契约（毫秒级，零外部依赖）。

背景：第三次完整 6 轮测试暴露的不是 AlphaPilot 执行能力问题，而是
「R5→R10 多轮题面互相打架」——R6 要求 PATCH/201，R10 冻结契约是 PUT/200；
R6 要 customer_name，R10 把它列为禁止字段；R10 还声称服务文件已存在。
这类矛盾要跑满 800 秒才会以 ImportError 的形式暴露，代价极高。

本文件把跨轮契约一致性做成静态检查：任何一次题面改动只要破坏单一事实源，
立刻在秒级失败，不需要启动 Docker / Redis / Worker / LLM。
"""

import importlib.util
import inspect
import re
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker.agents.qwen.step_runner import _extract_requested_paths  # noqa: E402

_OBS_FILE = Path(__file__).with_name("test_observe_task_system.py")

# 形如 "- POST / → 200" 或 "* PUT /{order_id}/status 返回 200"
_ENDPOINT_RE = re.compile(
    r"^\s*[-*]\s+(POST|GET|PUT|DELETE|PATCH)\s+(/[^\s→]*)\s*(?:→|返回)\s*(\d{3})",
    re.MULTILINE,
)


@pytest.fixture(scope="module")
def obs():
    spec = importlib.util.spec_from_file_location("shopflow_observe_mod", _OBS_FILE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _endpoints(text: str) -> list:
    return [(m, p, int(s)) for m, p, s in _ENDPOINT_RE.findall(text)]


def _r10_sections(obs) -> tuple:
    t = obs._PROMPT_ROUND_10_TEMPLATE
    a = t.index("3. 修改 backend/routers/orders.py")
    b = t.index("4. 修改 backend/routers/inventory.py", a)
    c = t.index("5. 不改变", b)
    return t[a:b], t[b:c]


def _expected(obs, router: str) -> list:
    return [
        (e["method"], e["path"], e["status_code"])
        for e in obs.SERVICE_LAYER_CONTRACT["router_contract"][router]
    ]


def test_round6_router_contract_matches_single_source(obs):
    """R6 题目里的端点/状态码必须与 R10 冻结契约逐项一致。"""
    assert _endpoints(obs.PROMPT_ROUND_6) == _expected(obs, "orders")


def test_round8_router_contract_matches_single_source(obs):
    assert _endpoints(obs.PROMPT_ROUND_8) == _expected(obs, "inventory")


def test_round10_router_contract_matches_single_source(obs):
    orders_sec, inv_sec = _r10_sections(obs)
    assert _endpoints(orders_sec) == _expected(obs, "orders")
    assert _endpoints(inv_sec) == _expected(obs, "inventory")


def test_all_rounds_reject_patch_on_orders(obs):
    """R5 曾写 PATCH /orders/{id}/status，与冻结契约的 PUT 冲突。"""
    for name in ("PROMPT_ROUND_5", "PROMPT_ROUND_6", "PROMPT_ROUND_9"):
        text = getattr(obs, name)
        assert not re.search(r"PATCH\s+/orders", text), name
    orders_sec, _ = _r10_sections(obs)
    assert "PATCH" not in orders_sec


def test_no_round_asks_for_forbidden_schema_or_symbol(obs):
    """R6 曾要求 OrderUpdate / customer_name，R10 又把它们列为禁止项。"""
    for name in ("PROMPT_ROUND_5", "PROMPT_ROUND_6", "PROMPT_ROUND_8",
                 "PROMPT_ROUND_9"):
        text = getattr(obs, name)
        assert "customer_name" not in text, name
        assert not re.search(r"(?:import|class)\s+OrderItem", text), name
    assert "OrderUpdateStatus" in obs.PROMPT_ROUND_6
    assert not re.search(r"\bOrderUpdate\b", obs.PROMPT_ROUND_6)


def test_r10_creates_services_instead_of_assuming_they_exist(obs):
    """R10 曾声称 order_service.py 已存在，但 R5-R9 从未要求生成它。"""
    t = obs._PROMPT_ROUND_10_TEMPLATE
    assert "该文件已存在" not in t
    assert t.count("必须创建") >= 2
    assert "backend/services/__init__.py" in t
    assert "backend/services/order_service.py" in t
    assert "backend/services/inventory_service.py" in t
    assert "禁止修改 tests/ 下任何文件" in t
    assert "backend/main.py 属于受保护文件" in t
    assert t.count("def __init__(self, db):") >= 2


def test_r10_router_paths_are_relative(obs):
    """R10 曾把端点写成 /orders/ 绝对路径，会与 main.py 的 prefix 叠加。"""
    for sec in _r10_sections(obs):
        for method, path, _ in _endpoints(sec):
            assert not path.startswith(("/orders", "/inventory")), (method, path)
    assert "next_states() 派生" in obs._PROMPT_ROUND_10_TEMPLATE


def test_router_prefix_is_owned_by_main_only(obs):
    """router 自带 prefix + main 再挂 prefix，会把路径叠成 /orders/orders。"""
    for name in ("PROMPT_ROUND_6", "PROMPT_ROUND_8"):
        assert "不要给 APIRouter() 传 prefix" in getattr(obs, name), name
    orders_sec, inv_sec = _r10_sections(obs)
    assert "不要给 APIRouter() 传 prefix" in orders_sec
    assert "不要给 APIRouter() 传 prefix" in inv_sec


def test_r9_status_values_match_frozen_enum_contract(obs):
    values = obs.SERVICE_LAYER_CONTRACT["enum_contract"]["values"]
    t = obs.PROMPT_ROUND_9
    for v in values:
        assert v in t, v
    for old in ("confirmed", "shipped", "delivered"):
        assert old in t, old
    assert "next_states()" in t
    assert "tests/test_orders.py" in t
    for v in values:
        assert v in obs._PROMPT_ROUND_10_TEMPLATE, v


def test_r5_document_request_matches_architect_policy(obs):
    """架构师模式只放行 docs/ 下带 architecture 的文档，题面必须明确点名并要求保存。"""
    from python_worker.collaboration_modes import (
        _is_architecture_document_operation,
        _requests_architecture_document,
    )

    assert "docs/architecture_design.md" in obs.PROMPT_ROUND_5
    assert _requests_architecture_document(obs.PROMPT_ROUND_5)
    assert _is_architecture_document_operation(
        {"path": "docs/architecture_design.md", "content": "# design"}
    )
    assert not _is_architecture_document_operation(
        {"path": "backend/main.py", "content": "x"}
    )
    assert _extract_requested_paths(obs.PROMPT_ROUND_5) == [
        "docs/architecture_design.md"
    ]
    from python_worker.agents.qwen.step_runner import _GUARD_INTENTS
    assert "architecture" in _GUARD_INTENTS


def test_r6_fixture_contract_prevents_missing_tables(obs):
    """R6 曾生成内存库夹具却没建表，R8 直接炸出 no such table。"""
    p = obs.PROMPT_ROUND_6
    for token in ("tests/conftest.py", "sqlite:///:memory:", "StaticPool",
                  "Base.metadata.create_all(bind=engine)",
                  "Base.metadata.drop_all(bind=engine)",
                  "app.dependency_overrides[get_db]"):
        assert token in p, token
    assert "from backend.models.order import Order" in p


def test_r8_registers_inventory_model_and_imports_it(obs):
    """R8 曾漏 import Inventory（NameError）+ 漏注册模型（no such table）。"""
    p = obs.PROMPT_ROUND_8
    assert "from backend.models.inventory import Inventory" in p
    assert "no such table: inventory" in p
    assert 'prefix="/inventory"' in p
    assert "不要改动 tests/conftest.py" in p
    assert "本轮不新建服务层" in p


def test_r6_empty_items_and_r8_bypass_are_paired(obs):
    """R8 加库存扣减后，R6 的存量测试若带非空 items 会全部变成 400。"""
    assert "items 统一传空列表 []" in obs.PROMPT_ROUND_6
    assert "items 为空时不检查" in obs.PROMPT_ROUND_8
    assert "不要修改 tests/test_orders.py" in obs.PROMPT_ROUND_8


def test_r7_bug_injection_contract_is_declared_in_r6(obs):
    """R7 靠精确字符串注入 Bug，R6 必须真的要求这一行 typing 导入。"""
    src = inspect.getsource(obs.inject_bug_remove_typing_import)
    assert "from typing import List" in obs.PROMPT_ROUND_6
    assert "from typing import List" in src


def test_prompts_never_name_misplaced_root_paths(obs):
    """锁死 models/enums.py、routers/inventory.py 这类丢前缀路径。"""
    allowed = ("backend/", "tests/", "docs/")
    for name in ("PROMPT_ROUND_5", "PROMPT_ROUND_6", "PROMPT_ROUND_8",
                 "PROMPT_ROUND_9"):
        for p in _extract_requested_paths(getattr(obs, name)):
            assert p.startswith(allowed), (name, p)
    for p in _extract_requested_paths(obs._PROMPT_ROUND_10_TEMPLATE):
        assert p.startswith(allowed), p


def test_forbidden_field_check_is_exact_match_not_substring(tmp_path, obs):
    """R8 的 unit_price 合法；检查器必须按精确属性名判定，不能把 price 当子串误杀。"""
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "sample.py").write_text(
        "obj.unit_price = 1\nOrder(customer_name='x')\n", encoding="utf-8"
    )
    contract = {
        "forbidden_fields": obs.SERVICE_LAYER_CONTRACT["forbidden_fields"],
        "models": {"Order": {"fields": {"customer_name": {}, "items": {}}}},
    }
    result = obs._check_orm_fields(tmp_path, contract)
    assert any("customer_name" in v for v in result["violations"])
    assert not any("unit_price" in v for v in result["violations"])


def test_model_contract_extraction_is_fail_closed(tmp_path, obs):
    """模型源码缺失时禁止生成「宽松版」R10 题面。"""
    result = obs._extract_model_contract(tmp_path)
    assert result["complete"] is False
    assert result["extraction_errors"]
