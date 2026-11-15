# -*- coding: utf-8 -*-
"""G10.27: OpenAI 兼容客户端不得把推理模型的思维链当成交付正文。

实测（DeepSeek MAAS / deepseek-v4-pro-0813）：
  非流式 message 里 content='OK'、reasoning_content='We need answer...'
  流式 delta 先连续吐 reasoning_content，content 为空。
旧实现 `content or reasoning_content` 会把整段思考文本 yield 出去，
write_step 会把它当代码 → extract_code / FileOp / 落盘。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from python_worker.agents.qwen.providers import openai_compatible_client as occ  # noqa: E402


def _client(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("OPENAI_MODEL", "reasoning-model")
    monkeypatch.setenv("OPENAI_RETRIES", "0")
    return occ.OpenAICompatibleClient()


class _FakeResponse:
    def __init__(self, payload=None, lines=None):
        self._payload = payload
        self._lines = lines or []
        self.encoding = "utf-8"

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload

    def iter_lines(self, decode_unicode=True):
        yield from self._lines

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _sse(delta):
    return "data: " + json.dumps({"choices": [{"delta": delta}]})


# ── 非流式 ────────────────────────────────────────────────────────

def test_nonstream_ignores_reasoning_only(monkeypatch):
    c = _client(monkeypatch)
    monkeypatch.setattr(
        occ.requests, "post",
        lambda *a, **k: _FakeResponse(payload={
            "choices": [{"message": {"reasoning_content": "We need answer..."}}]
        }),
    )
    assert c.call("hi") == ""


def test_nonstream_returns_content(monkeypatch):
    c = _client(monkeypatch)
    monkeypatch.setattr(
        occ.requests, "post",
        lambda *a, **k: _FakeResponse(payload={
            "choices": [{"message": {
                "content": "print(1)", "reasoning_content": "let me think"}}]
        }),
    )
    assert c.call("hi") == "print(1)"


def test_nonstream_prefers_content_when_both_present(monkeypatch):
    c = _client(monkeypatch)
    monkeypatch.setattr(
        occ.requests, "post",
        lambda *a, **k: _FakeResponse(payload={
            "choices": [{"message": {
                "content": "OK", "reasoning_content": "We need answer..."}}]
        }),
    )
    assert c.call("hi") == "OK"


# ── 流式 ──────────────────────────────────────────────────────────

def test_stream_emits_only_content_chunks(monkeypatch):
    c = _client(monkeypatch)
    lines = [
        _sse({"reasoning_content": "We need answer user asks"}),
        _sse({"reasoning_content": ". No quotes."}),
        _sse({"content": "OK", "reasoning_content": "final thinking"}),
        "data: [DONE]",
    ]
    monkeypatch.setattr(occ.requests, "post",
                        lambda *a, **k: _FakeResponse(lines=lines))
    assert "".join(c.call_stream("hi")) == "OK"


def test_stream_reasoning_only_produces_empty_text(monkeypatch):
    """纯思维链 → 空结果，交由上层 FAIL-CLOSED，绝不交付思考文本。"""
    c = _client(monkeypatch)
    lines = [_sse({"reasoning_content": "thinking..."}), "data: [DONE]"]
    monkeypatch.setattr(occ.requests, "post",
                        lambda *a, **k: _FakeResponse(lines=lines))
    assert "".join(c.call_stream("hi")) == ""


def test_stream_failure_still_yields_guard_marker(monkeypatch):
    """网络异常仍产出 [API 调用失败: 前缀，保证 G10.26 能拦截。"""
    c = _client(monkeypatch)

    def boom(*_a, **_k):
        raise ConnectionError("tunnel failed")

    monkeypatch.setattr(occ.requests, "post", boom)
    out = "".join(c.call_stream("hi"))
    assert "[API 调用失败:" in out


def test_source_has_no_reasoning_fallback():
    """源码级回归：禁止再把 reasoning_content 用 or 兜底进正文。"""
    src = Path(occ.__file__).read_text(encoding="utf-8")
    assert 'or msg.get("reasoning_content"' not in src
    assert 'or delta.get("reasoning_content"' not in src
