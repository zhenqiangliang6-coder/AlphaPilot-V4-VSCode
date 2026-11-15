# -*- coding: utf-8 -*-
"""SSE 流式响应 UTF-8 解码契约。

真实故障：ModelScope 返回 `Content-Type: text/event-stream`（无 charset），
requests 默认按 ISO-8859-1 解码，模型输出的中文在写进 .py/.md 之前就变成
mojibake，最终导致 `SyntaxError: invalid non-printable character`，
把一整轮端到端测试连同后续轮次全部带垮。

这些用例锁死：流式必须拿原始字节显式 UTF-8 解码（或显式声明 encoding），
不允许依赖 requests 的编码猜测。
"""

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker.agents.qwen.providers.modelscope_client import (  # noqa: E402
    ModelScopeClient,
)


class _FakeSSEResponse:
    """模拟 SSE 响应：只提供 UTF-8 原始字节。"""

    def __init__(self, lines):
        self._lines = lines
        self.status_code = 200

    def raise_for_status(self):
        return None

    def iter_lines(self, decode_unicode=False):
        # 主实现必须明确要求原始字节；若改回 True，requests 会按 latin-1 解码
        assert decode_unicode is False, "流式响应必须拿原始字节，不能让库猜编码"
        yield from self._lines

    def close(self):
        return None


def _sse_lines(text):
    payload = {"choices": [{"delta": {"content": text}}]}
    return [
        b"data: " + json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        b"data: [DONE]",
    ]


@pytest.mark.parametrize("text", [
    "中文正常",
    "订单状态 → 已完成",
    "客户名称：张三，备注：测试库存项",
])
def test_modelscope_stream_one_keeps_utf8(monkeypatch, text):
    c = ModelScopeClient()
    monkeypatch.setattr(c, "_post", lambda *a, **k: _FakeSSEResponse(_sse_lines(text)))

    out = "".join(c._stream_one("model", "prompt", 0.3, None))

    assert out == text
    assert "æ" not in out and "Ã" not in out and "\x8b" not in out


def test_modelscope_call_stream_utf8_end_to_end(monkeypatch):
    """完整 call_stream 路径（含降级链）也不能把中文弄坏。"""
    c = ModelScopeClient()
    c._api_key = "dummy"
    text = "订单状态：运输中"
    monkeypatch.setattr(c, "_post", lambda *a, **k: _FakeSSEResponse(_sse_lines(text)))

    out = "".join(c.call_stream("请输出中文状态描述"))

    assert out == text


def test_modelscope_stream_ignores_blank_and_done_lines(monkeypatch):
    c = ModelScopeClient()
    payload = {"choices": [{"delta": {"content": "正常"}}]}
    lines = [
        b"",
        b": ping",
        b"data: " + json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        b"data: [DONE]",
    ]
    monkeypatch.setattr(c, "_post", lambda *a, **k: _FakeSSEResponse(lines))

    assert "".join(c._stream_one("m", "p", 0.3, None)) == "正常"


def test_every_stream_client_declares_utf8():
    """静态契约：所有流式客户端都必须显式处理 UTF-8，防止换 Provider 后复发。"""
    base = _PROJECT_ROOT / "python_worker" / "agents" / "qwen"
    targets = [
        base / "providers" / "modelscope_client.py",
        base / "providers" / "qwen_client.py",
        base / "providers" / "deepseek_client.py",
        base / "providers" / "openai_compatible_client.py",
        base / "qwen_api.py",
    ]
    for f in targets:
        src = f.read_text(encoding="utf-8")
        assert ('encoding = "utf-8"' in src
                or 'decode("utf-8"' in src), f"{f.name} 缺少显式 UTF-8 解码防护"
