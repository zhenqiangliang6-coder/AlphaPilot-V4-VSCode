# python_worker/tests/test_model_quota_circuit.py
"""QwenClient 模型级免费额度熔断回归契约。

真实故障（2026-11-14/15）：DashScope qwen3.7-flash / qwen3.7-max 返回
`403 Free quota exhausted`（模型级免费额度耗尽，非 Provider 整体故障），
Worker 每个执行步骤都要先白撞两次 403 才降级成功，R7 单轮多耗数分钟。

契约：
- 某模型返回 403 Free quota exhausted → 该模型被摘除，本进程后续直接跳过；
- 正常 200 的下一模型照常工作（不熔断整个 Provider）；
- 候选链全部耗尽时返回明确的失败信息，而不是空结果；
- reset_exhausted_models() 可清除（运维领到额度后无需重启进程）。
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

import pytest


class _FakeResp:
    def __init__(self, status, text):
        self.status_code = status
        self.text = text
        self.encoding = None

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_lines(self, decode_unicode=True):
        if self.status_code != 200:
            return iter([])
        # G10.36 起「流结束但零正文」明确判失败，G10.38 起还会把该模型
        # 摘入流式失败冷却。本文件里的 200 是「正常可用模型」占位，
        # 必须给真实正文，否则测的就不是额度熔断而是零正文防护了。
        import json
        return iter([
            "data: " + json.dumps({"choices": [{"delta": {"content": "ok"}}]}),
            "data: [DONE]",
        ])


def _make_client(monkeypatch, models):
    from python_worker.agents.qwen.providers import qwen_client
    import python_worker.worker_config as wc
    monkeypatch.setattr(wc, "DASHSCOPE_API_KEY", "dummy-key")
    client = qwen_client.QwenClient()
    monkeypatch.setattr(client, "_get_chain", lambda: list(models))
    return client, qwen_client


def test_quota_403_marks_and_skips_next_call(monkeypatch):
    """首次 403 额度耗尽 → 标记；第二次调用直接跳过该模型。"""
    client, qc = _make_client(monkeypatch, ["m-a", "m-b"])
    qc.reset_exhausted_models()
    calls = []

    def post(url, **kw):
        model = kw["json"]["model"]
        calls.append(model)
        if model == "m-a":
            return _FakeResp(403, '{"error":{"message":"Free quota exhausted. ..."}}')
        return _FakeResp(200, "{}")

    monkeypatch.setattr(client._session, "post", post)
    list(client.call_stream("hi"))
    assert "m-a" in qc.exhausted_models()
    assert calls == ["m-a", "m-b"], calls

    # 第二次调用：m-a 不再被请求，直接走 m-b
    calls.clear()
    list(client.call_stream("hi"))
    assert calls == ["m-b"], calls
    qc.reset_exhausted_models()
    assert not qc.exhausted_models()


def test_other_403_not_marked(monkeypatch):
    """普通 403（权限类）不触发模型摘除，避免误摘。"""
    client, qc = _make_client(monkeypatch, ["m-a", "m-b"])
    qc.reset_exhausted_models()

    def post(url, **kw):
        return _FakeResp(403, '{"error":{"message":"Forbidden ARMS"}}')

    monkeypatch.setattr(client._session, "post", post)
    out = "".join(client.call_stream("hi"))
    assert "m-a" not in qc.exhausted_models()
    assert "所有模型不可用" in out
    qc.reset_exhausted_models()


def test_all_models_exhausted_message(monkeypatch):
    """候选链全部耗尽 → 明确报错而非静默空结果。"""
    client, qc = _make_client(monkeypatch, ["m-a", "m-b"])
    qc.reset_exhausted_models()
    qc._mark_model_exhausted("m-a")
    qc._mark_model_exhausted("m-b")
    out = "".join(client.call_stream("hi"))
    assert "免费额度均已耗尽" in out
    qc.reset_exhausted_models()


def test_normal_200_not_affected(monkeypatch):
    """额度未耗尽的模型不受影响（熔断只针对 403 quota exhausted）。"""
    client, qc = _make_client(monkeypatch, ["m-a"])
    qc.reset_exhausted_models()

    def post(url, **kw):
        return _FakeResp(500, "server error")

    monkeypatch.setattr(client._session, "post", post)
    out = "".join(client.call_stream("hi"))
    assert "m-a" not in qc.exhausted_models()
    assert "所有模型不可用" in out
    qc.reset_exhausted_models()


# ── G10.18: 按步骤路由模型 ────────────────────────────────────────

def _routing_env(monkeypatch):
    from python_worker.agents.qwen import qwen_model_probe as probe
    monkeypatch.setenv("QWEN_MODEL", "qwen3.6-plus")
    monkeypatch.setenv("QWEN_FALLBACK_1", "qwen3.5-plus")
    monkeypatch.setenv("QWEN_FALLBACK_2", "qwen-plus")
    monkeypatch.setenv("QWEN_FALLBACK_3", "qwen3.6-plus")
    monkeypatch.setenv("QWEN_FAST_MODEL", "qwen-plus")
    return probe


def test_fast_step_uses_fast_model_first(monkeypatch):
    """analyze/doc 等样板步骤优先快模型，强模型仍留在降级链里兜底。"""
    probe = _routing_env(monkeypatch)
    probe.set_step_model_hint("doc")
    chain = probe.get_text_fallback_chain()
    assert chain[0] == "qwen-plus"
    assert "qwen3.6-plus" in chain
    assert len(chain) == len(set(chain))
    probe.set_step_model_hint(None)


def test_code_steps_keep_strong_model(monkeypatch):
    """write/refine/fix 与闸门修复（无 hint）必须用强模型，保证生成质量。"""
    probe = _routing_env(monkeypatch)
    for hint in ("write", "refine", "fix", None, "unknown_step"):
        probe.set_step_model_hint(hint)
        assert probe.get_text_fallback_chain()[0] == "qwen3.6-plus", hint
    probe.set_step_model_hint(None)


def test_fast_model_disabled_falls_back_to_strong(monkeypatch):
    """未配置 QWEN_FAST_MODEL 时路由完全不生效（FAIL-OPEN）。"""
    probe = _routing_env(monkeypatch)
    monkeypatch.delenv("QWEN_FAST_MODEL")
    probe.set_step_model_hint("analyze")
    assert probe.get_text_fallback_chain()[0] == "qwen3.6-plus"
    probe.set_step_model_hint(None)


def test_architecture_intent_uses_fast_model_even_for_write(monkeypatch):
    """G10.20：R5 架构文档只产出 Markdown，write 步骤也走快模型。"""
    probe = _routing_env(monkeypatch)
    probe.set_step_model_hint("write", "architecture")
    assert probe.get_text_fallback_chain()[0] == "qwen-plus"
    probe.set_step_model_hint(None)


def test_write_code_intent_keeps_strong_model(monkeypatch):
    """写码轮不受架构意图快链影响，仍用强模型。"""
    probe = _routing_env(monkeypatch)
    probe.set_step_model_hint("write", "write_code")
    assert probe.get_text_fallback_chain()[0] == "qwen3.6-plus"
    probe.set_step_model_hint(None)
