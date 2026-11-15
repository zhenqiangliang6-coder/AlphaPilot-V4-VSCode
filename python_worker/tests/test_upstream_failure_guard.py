# -*- coding: utf-8 -*-
"""G10.26: 上游模型失败文本 FAIL-CLOSED 契约。

背景（v7 实证）：qwen_client.call_stream() 在整条降级链全挂时不抛异常，
而是 yield 一段可读的错误文本。旧实现把它当正常生成内容继续走
extract_code → 单文件降级 → FileOp → DeliveryGate → EvidenceGate，
最终任务写 awaiting_authorization、验收判「执行成功」，但实际零产出。
R9 日志证据：新值 []、残留旧值未减少、修改文件全是 R8 的历史文件。
"""
import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from python_worker.agents.qwen.step_executor import utils, write_step as ws  # noqa: E402


REAL_FAILURE_TEXT = (
    "\n\n[API 调用失败: 所有模型不可用 - HTTPSConnectionPool("
    "host='dashscope.aliyuncs.com', port=443): Max retries exceeded]"
)


# ── 判定函数：命中上游失败，且不误伤正常代码 ──────────────────────

@pytest.mark.parametrize("text", [
    REAL_FAILURE_TEXT,
    "\n\n[API 调用失败: 候选链模型免费额度均已耗尽(403)，请领取额度或切换 Provider]",
    "[API 调用失败: 所有模型不可用 - 模型 qwen3.5-plus 免费额度耗尽(403)]",
    "# LLM 调用失败: ConnectTimeout",
])
def test_failure_texts_are_detected(text):
    assert utils.is_upstream_failure_text(text) is True


@pytest.mark.parametrize("text", [
    "",
    "def create_order(db, payload):\n    return db.add(payload)\n",
    "# FILE: backend/models/order.py\nclass Order: pass\n",
    "# 注意：这里讨论「所有模型不可用」时应该如何降级（设计文档）",
    "# 候选链模型免费额度均已耗尽(403) 是上游的一种错误",
    "print('所有模型不可用')",
])
def test_normal_text_is_not_flagged(text):
    """自然语言片段不参与判定，正常代码 / 文档 / 字符串不受影响。"""
    assert utils.is_upstream_failure_text(text) is False


def test_error_marker_embedded_after_partial_stream_is_still_caught():
    """流式先吐了几个字再断，错误标记不在开头也必须拦截。"""
    text = "部分内容\n\n[API 调用失败: 所有模型不可用 - timeout]"
    assert utils.is_upstream_failure_text(text) is True


@pytest.mark.parametrize("value", [None, 123, [], {}, object()])
def test_non_string_input_is_not_flagged(value):
    assert utils.is_upstream_failure_text(value) is False


# ── write_step：错误文本不得生成 FileOp，正常文本照常生成 ──────────

def _context():
    return {
        "meta": {"intent": "write_code", "persona": "engineer",
                 "user_request": "级联替换枚举值", "workspace_path": ""},
        "intermediate_results": [{"type": "plan", "plan": "替换枚举值"}],
        "final_file_ops": [],
    }


def _run_with_text(monkeypatch, text):
    monkeypatch.setattr(ws, "_needs_multi_round", lambda _p: False)
    monkeypatch.setattr(ws, "write_prompt", lambda *a, **k: "prompt")
    monkeypatch.setattr(ws, "call_llm_with_persona", lambda *a, **k: text)
    monkeypatch.setattr(ws, "call_llm", lambda *a, **k: text)
    monkeypatch.setattr(ws, "create_event", lambda *a, **k: {"ok": True})
    ctx = _context()
    step = {"input": {"prompt": ""}}
    events = []
    ws.run_write_step(step, ctx, events, task_id=None)
    return ctx, step


def test_failure_text_produces_no_file_op(monkeypatch):
    ctx, step = _run_with_text(monkeypatch, REAL_FAILURE_TEXT)
    assert step["output"]["file_ops"] == []
    assert step["output"]["file_ops_count"] == 0
    assert step["output"]["llm_success"] is False
    assert step["output"]["code"] == ""
    assert ctx.get("upstream_failure"), "必须留下可供 Worker 判定失败状态的证据"
    assert ctx["meta"].get("upstream_failure") is True
    assert ctx["final_file_ops"] == [], "不得把错误文本写进交付清单"


def test_normal_text_still_produces_file_op(monkeypatch):
    """反证：不是一刀切禁用生成，正常 LLM 输出仍走原有单文件降级。"""
    ctx, step = _run_with_text(monkeypatch, "def hello():\n    return 1\n")
    assert not ctx.get("upstream_failure")
    assert step["output"]["llm_success"] is True
    assert step["output"]["file_ops_count"] >= 1
    assert ctx["final_file_ops"], "正常输出必须照常进入 final_file_ops"


# ── Worker 结果状态：上游失败不得发布成功状态 ──────────────────────

def test_worker_marks_upstream_failure_as_failed():
    src = (Path(__file__).resolve().parents[1]
           / "agents/qwen/qwen_worker_v2.py").read_text(encoding="utf-8")
    assert "G10.26" in src
    assert 'context.get("upstream_failure")' in src
    assert 'raise RuntimeError(' in src
    assert "上游模型不可用，任务未生成有效代码（FAIL-CLOSED）" in src
    ast.parse(src)


def test_write_step_guard_is_wired_before_extraction():
    """拦截点必须在 extract_code / parse_fileops_v3 之前，否则仍会落盘。"""
    src = Path(ws.__file__).read_text(encoding="utf-8")
    guard = src.find("_upstream_failure = is_upstream_failure_text(result)")
    extraction = src.find("code = \"\" if _upstream_failure else extract_code")
    parsing = src.find("parse_fileops_v3(result)")
    assert guard != -1 and extraction != -1 and parsing != -1
    assert guard < extraction < parsing
