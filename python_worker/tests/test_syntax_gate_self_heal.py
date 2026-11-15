# -*- coding: utf-8 -*-
"""回归契约：Python FileOps 落盘前的语法自愈（FAIL-CLOSED → FAIL-SAFE）。

真实故障（2026-11-14 第五次完整测试 shopflow_run8.log）：
  R6 生成的 tests/conftest.py 第 42 行混入一句裸英文
    "Optimized the FastAPI + SQLAlchemy e-commerce order management system ..."
  → ImportError/SyntaxError，R6 质量失败；R7–R10 全部因「前置 pytest 未通过」
    连锁失败（6 failed, 1 passed）。
  根因不在模型偶发输出，而在 finalize_task() 的 v3.4 语法门控：
    compile() 报错后只写 _needs_fix 标记，注释明说「但任务将继续发布」。
    R6 的 test_step 停在 awaiting_authorization，自愈轮次被跳过，
    于是脏文件被 Node API 原样写盘。

修复：python_worker/agents/qwen/step_runner.py
  - 新增 _repair_python_content()：仅尾部剥离、被剥离行必须无法独立
    parse 成 Python 语句、候选必须重新 compile() 通过才采纳；
  - 门控在标记 _needs_fix 之前先原地修复 _fop["content"]。

本契约同时锁死「自愈本身不得误删合法代码」。
"""
from pathlib import Path

from python_worker.agents.qwen.step_runner import (
    _is_discardable_prose,
    _repair_python_content,
)

_ROOT = Path(__file__).resolve().parents[2]
_RUNNER = _ROOT / "python_worker" / "agents" / "qwen" / "step_runner.py"

PROSE = (
    "Optimized the FastAPI + SQLAlchemy e-commerce order management system "
    "for production readiness, focusing on type safety, transaction integrity, "
    "modern ORM syntax, and test reliability."
)

# 第二次完整测试（shopflow_run9）真实污染样本：
# tests/test_orders.py:82 → SyntaxError: invalid character '→' (U+2192)
MARKDOWN_PROSE = "`pending` → `confirmed` / `cancelled`  "

VALID_CONFTEST = '''import pytest
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
'''


def test_detects_real_r6_pollution_and_repairs():
    dirty = VALID_CONFTEST + "\n" + PROSE + "\n"
    repaired, cut = _repair_python_content(dirty, "tests/conftest.py")
    assert repaired is not None
    assert cut >= 1
    compile(repaired, "tests/conftest.py", "exec")  # 修复结果必须真能编译
    assert "TestClient" in repaired
    assert "yield c" in repaired
    assert PROSE not in repaired


def test_detects_markdown_status_note_pollution():
    """带反引号/Unicode 箭头的 Markdown 行也必须被自愈剥离。"""
    assert _is_discardable_prose(MARKDOWN_PROSE) is True
    dirty = VALID_CONFTEST + "\n" + MARKDOWN_PROSE + "\n"
    repaired, cut = _repair_python_content(dirty, "tests/test_orders.py")
    assert repaired is not None
    assert cut >= 1
    compile(repaired, "tests/test_orders.py", "exec")
    assert "→" not in repaired
    assert "yield c" in repaired


def test_valid_code_is_never_modified():
    assert _repair_python_content(VALID_CONFTEST, "tests/conftest.py") == (None, 0)


def test_prose_detection_never_eats_code_or_comments():
    assert _is_discardable_prose(PROSE) is True
    # 空行/注释属于正常文件内容，不是污染（空行只在定位尾部时被跳过）
    assert _is_discardable_prose("") is False
    assert _is_discardable_prose("   \n") is False
    assert _is_discardable_prose("# 正常注释") is False
    assert _is_discardable_prose("x = 1") is False
    assert _is_discardable_prose("import pytest") is False
    assert _is_discardable_prose("def foo():") is False
    assert _is_discardable_prose("    with TestClient(app) as c:") is False
    assert _is_discardable_prose("        yield c") is False


def test_mid_file_syntax_error_is_not_masked_by_deletion():
    """测试故意注入的 Bug 不能被自愈悄悄删掉，那会破坏测试语义。"""
    dirty = "from typing import   # ← BUG: List removed\n\nx = 1\n"
    assert _repair_python_content(dirty, "backend/routers/orders.py") == (None, 0)


def test_repair_is_bounded():
    """超长污染不得把文件越删越空，必须有明确上界。"""
    dirty = "x = 1\n" + (PROSE + "\n") * 20
    assert _repair_python_content(dirty, "x.py") == (None, 0)


def test_finalize_gate_self_heals_before_marking_needs_fix():
    """静态锁死门控：先自愈并原地写回 content，再考虑标记 _needs_fix。"""
    src = _RUNNER.read_text(encoding="utf-8")
    gate = src.split("# ===== v3.4+:", 1)[1].split("# ===== v3.5:", 1)[0]
    assert "_repair_python_content(_fcontent, _fpath)" in gate
    assert '_fop["content"] = _repaired' in gate
    assert 'context["meta"]["_syntax_self_healed"]' in gate
    assert "但任务将继续发布" not in gate
