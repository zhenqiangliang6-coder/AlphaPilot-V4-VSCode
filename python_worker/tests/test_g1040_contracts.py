# python_worker/tests/test_g1040_contracts.py
"""G10.40 保护「题面显式 ORM 契约不被放宽」的回归契约。

真实故障（shopflow_v19_1，2026-11-15 18:39–18:50）：
`1 failed, 6 passed in 630.43s`，R5–R9 **五轮四维全绿**，唯独 R10
在生成 PROMPT 前抛 `ContractExtractionError`。

取证：`PROMPT_ROUND_6` 逐字要求
「Order 模型必须用 SQLAlchemy 经典 Column(...) 写法」
「订单项统一放在 items JSON 列里，不设独立 ORM 表」
「不要新建订单项模型类」「user_id 字段」；
而 G10.38 引入的 `deepseek-v4.1-flash`（长提示快 6 倍）在 R6 生成了
`Mapped[...] / mapped_column(...)`、`OrderItem` 独立表 + relationship、
`customer_id` 字段。R6 质量门只看 pytest 与文件存在，没查这条语义约束，
于是缺陷潜伏到 R10 —— `_extract_model_contract` 从真实源码提取模型契约
时 FAIL-CLOSED，判定「暂不支持的 ORM 声明方式」，禁止生成 PROMPT。

决策：**不扩展测试提取器去兼容 2.0 风格**，那等于把题面明令禁止的写法
变成合法，属于放宽验收。主链改回 v17 已验证会逐字遵守该契约的
`qwen3.7-max-preview`，deepseek 降为快速兜底；G10.38 的失败模型摘链 /
指数退避 / 45s 首正文与 G10.39 的 import 头重建全部保留。

本文件把「题面约束 + 提取器严格性 + 主链配置」钉成契约，防止后续
为了提速又悄悄放宽其中任何一环。
"""

import ast
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker.tests import test_observe_task_system as obs  # noqa: E402


_MAPPED_ORDER = '''"""Order ORM model."""
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer, nullable=False)
    items: Mapped[list] = relationship("OrderItem")
'''

_CLASSIC_ORDER = '''"""Order ORM model."""
from sqlalchemy import Column, Integer, String, JSON
from backend.database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), nullable=False)
    items = Column(JSON, nullable=False, default=list)
'''

_INVENTORY = '''"""Inventory ORM model."""
from sqlalchemy import Column, Integer
from backend.database import Base


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True)
'''

_ENUMS = '''from enum import Enum


class OrderStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
'''


def _workspace(tmp_path, order_src):
    d = tmp_path / "backend" / "models"
    d.mkdir(parents=True)
    (d / "order.py").write_text(order_src, encoding="utf-8")
    (d / "inventory.py").write_text(_INVENTORY, encoding="utf-8")
    (d / "enums.py").write_text(_ENUMS, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------- 题面契约

def test_round6_prompt_explicitly_forbids_2x_orm_style():
    p = obs.PROMPT_ROUND_6
    assert "经典 Column(...) 写法" in p
    assert "不设独立 ORM 表" in p
    assert "不要新建订单项模型类" in p
    assert "items JSON 列" in p
    assert "user_id" in p


def test_round8_prompt_also_requires_classic_column():
    assert "经典 Column(...) 写法" in obs.PROMPT_ROUND_8


# ---------------------------------------------------------------- 提取器严格性

def test_mapped_style_is_reported_incomplete_not_silently_accepted():
    node = ast.parse(_MAPPED_ORDER).body[-1]
    errors = []
    assert obs._parse_orm_class(node, "backend/models/order.py", errors) is None
    assert len(errors) == 1
    assert "暂不支持的 ORM 声明方式" in errors[0]
    assert "id" in errors[0] and "customer_id" in errors[0]


def test_classic_column_style_extracts_full_contract():
    node = ast.parse(_CLASSIC_ORDER).body[-1]
    errors = []
    model = obs._parse_orm_class(node, "backend/models/order.py", errors)
    assert errors == []
    assert model["tablename"] == "orders"
    assert model["primary_key_field"] == "id"
    assert model["fields"]["items"]["is_json"] is True
    assert "user_id" in model["fields"]


def test_build_semantic_contract_is_fail_closed_on_mapped_style(tmp_path):
    ws = _workspace(tmp_path, _MAPPED_ORDER)
    with pytest.raises(obs.ContractExtractionError) as ei:
        obs._build_semantic_contract(ws)
    msg = str(ei.value)
    assert "禁止生成 PROMPT" in msg
    assert "暂不支持的 ORM 声明方式" in msg


def test_build_semantic_contract_accepts_classic_style(tmp_path):
    ws = _workspace(tmp_path, _CLASSIC_ORDER)
    contract = obs._build_semantic_contract(ws)
    assert "Order" in contract["models"]
    assert "Inventory" in contract["models"]


# ---------------------------------------------------------------- 通道配置契约

def test_main_chain_uses_contract_compliant_model():
    """速度不能凌驾于题面契约：主链必须是已验证遵守 Column 写法的模型。"""
    env = (_PROJECT_ROOT / "python_worker" / ".env").read_text(encoding="utf-8")
    pairs = {}
    for line in env.splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        pairs[k.strip()] = v.strip()
    assert pairs["QWEN_MODEL"] == "qwen3.7-max-preview"
    assert pairs["QWEN_FAST_MODEL"] == "qwen3.7-max-preview"
    assert "deepseek-v4.1-flash" in (pairs["QWEN_FALLBACK_1"],
                                     pairs["QWEN_FALLBACK_2"])
    assert pairs["QWEN_STREAM_FIRST_CONTENT_SEC"] == "45"
    # v32 起上游 dashscope 间歇抖动，主链切到魔搭免费通道；两个通道的
    # 主链模型都必须是守约的 qwen3.7-max-preview（模型名约束不放宽），
    # 仅 provider 开关允许 qwen / modelscope 二选一。
    assert pairs["LLM_PROVIDER"] in ("qwen", "modelscope")


def test_g1038_governance_is_still_enabled():
    """回切主链不得把 G10.38/G10.39 的治理一起回退。"""
    from python_worker.agents.qwen.providers import qwen_client as qc
    assert qc.stream_first_content_sec() == 45.0
    assert qc.stream_fail_cooldown_sec() == 600.0
    assert qc.quota_cooldown_sec.__doc__ and "指数退避" in qc.quota_cooldown_sec.__doc__
    from python_worker.delivery_gate import _repair_orphan_import_block
    assert callable(_repair_orphan_import_block)
