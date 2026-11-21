# python_worker/tests/test_g1036_stream_thinking_guard.py
"""G10.36 推理模型流式挂死防护契约。

真实故障（shopflow_v15_1，2026-11-15 15:42–16:12）：R5 四维全绿，
R6 `core_implementation` 提交后 Worker 静默挂死 1800s 直到轮询超时，
R7–R10 因「R6 未产出必要文件」连锁失败，一遍 `6 failed, 1 passed in 2157s`。

实测证据（同日 16:2x，长 prompt 直连 DashScope）：
- `qwen3.8-27b` 默认：75s 吐 15182 字符 `reasoning_content`，**零正文**，
  2643 行 SSE 且未结束；客户端只取 `delta.content`，一个 chunk 都不 yield。
- SSE 持续有数据 ⇒ requests 的 45s **read** timeout 永不触发
  （它只管相邻 chunk 间隔，不是一次调用的总时长上界）。
- 同模型 `enable_thinking=False`：0.55s 首正文，12.4s 完成，3117 字符代码。
- `qwen3.8-2.4t-a95b` / `qwen3.7-max-preview` 会 400 拒绝关思考参数，
  所以只能按模型配置下发，并保留 400 自动回退。

契约：关思考按模型配置 + 400 回退；单次流有墙钟/首正文双上界；
零正文判失败换模型；已有正文后超时立即 FAIL-CLOSED 且不换模型重生成，
避免把两个模型的半截输出拼成一份损坏文件。
"""

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _qc(monkeypatch):
    from python_worker.agents.qwen.providers import qwen_client
    import python_worker.worker_config as wc
    monkeypatch.setattr(wc, "DASHSCOPE_API_KEY", "dummy-key")
    monkeypatch.delenv("QWEN_NO_THINK_MODELS", raising=False)
    monkeypatch.delenv("QWEN_STREAM_WALL_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("QWEN_STREAM_FIRST_CONTENT_SEC", raising=False)
    return qwen_client


class _FakeResp:
    def __init__(self, status=200, lines=None, text=""):
        self.status_code = status
        self._lines = lines or []
        self.text = text
        self.encoding = None
        self.closed = False
        self.body = None

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_lines(self, decode_unicode=False):
        yield from self._lines

    def close(self):
        self.closed = True


def _sse(content=None, reasoning=None):
    delta = {}
    if content is not None:
        delta["content"] = content
    if reasoning is not None:
        delta["reasoning_content"] = reasoning
    return "data: " + json.dumps({"choices": [{"delta": delta}]}, ensure_ascii=False)


def _client(monkeypatch, models, responses):
    qc = _qc(monkeypatch)
    qc.reset_exhausted_models()
    client = qc.QwenClient()
    monkeypatch.setattr(client, "_get_chain", lambda: list(models))
    calls = []
    queue = list(responses)

    def post(url, **kw):
        calls.append(kw["json"])
        return queue.pop(0)

    monkeypatch.setattr(client._session, "post", post)
    return qc, client, calls


class _FakeClock:
    """每次 monotonic() 推进 step 秒，模拟只吐思考、迟迟不给正文的流。"""

    def __init__(self, step=1.0):
        self.t = 0.0
        self.step = step

    def monotonic(self):
        self.t += self.step
        return self.t

    def sleep(self, _sec):
        return None


# ---------------------------------------------------------------- 纯函数契约

def test_build_stream_body_only_disables_thinking_when_asked(monkeypatch):
    qc = _qc(monkeypatch)
    plain = qc.build_stream_body("m", "p", 0.2, False)
    off = qc.build_stream_body("m", "p", 0.2, True)
    assert "enable_thinking" not in plain
    assert off["enable_thinking"] is False
    assert off["model"] == "m" and off["stream"] is True
    assert off["messages"] == [{"role": "user", "content": "p"}]


def test_no_think_models_default_and_env_override(monkeypatch):
    qc = _qc(monkeypatch)
    assert qc.wants_no_thinking("qwen3.8-27b")
    assert not qc.wants_no_thinking("qwen3.7-max-preview")
    monkeypatch.setenv("QWEN_NO_THINK_MODELS", "model-a, model-b")
    assert qc.wants_no_thinking("model-b")
    assert not qc.wants_no_thinking("qwen3.8-27b")


def test_is_enable_thinking_rejected(monkeypatch):
    qc = _qc(monkeypatch)
    assert qc.is_enable_thinking_rejected(
        _FakeResp(400, text="The value of the enable_thinking parameter is restricted to True."))
    assert not qc.is_enable_thinking_rejected(_FakeResp(400, text="bad model"))
    assert not qc.is_enable_thinking_rejected(_FakeResp(200, text="enable_thinking"))


def test_timeout_defaults_and_env_clamps(monkeypatch):
    qc = _qc(monkeypatch)
    assert qc.stream_wall_timeout_sec() == 240.0
    # G10.38：首正文上界按实测收紧到 45s（v17 的 90s 让失败步骤各白等 90s）
    assert qc.stream_first_content_sec() == 45.0
    monkeypatch.setenv("QWEN_STREAM_WALL_TIMEOUT_SEC", "35")
    monkeypatch.setenv("QWEN_STREAM_FIRST_CONTENT_SEC", "not-a-number")
    assert qc.stream_wall_timeout_sec() == 35.0
    assert qc.stream_first_content_sec() == 45.0


# ---------------------------------------------------------------- 流式行为契约

def test_configured_model_gets_enable_thinking_false(monkeypatch):
    qc, client, calls = _client(
        monkeypatch, ["qwen3.8-27b"],
        [_FakeResp(200, [_sse(content="print(1)"), "data: [DONE]"])])
    assert "".join(client.call_stream("write code")) == "print(1)"
    assert calls[0]["enable_thinking"] is False


def test_non_configured_model_keeps_default_mode(monkeypatch):
    qc, client, calls = _client(
        monkeypatch, ["qwen3.7-max-preview"],
        [_FakeResp(200, [_sse(content="ok"), "data: [DONE]"])])
    assert "".join(client.call_stream("hi")) == "ok"
    assert "enable_thinking" not in calls[0]


def test_400_on_enable_thinking_retries_without_param(monkeypatch):
    qc, client, calls = _client(
        monkeypatch, ["qwen3.8-27b"],
        [_FakeResp(400, text="The value of the enable_thinking parameter is restricted to True."),
         _FakeResp(200, [_sse(content="fallback-ok"), "data: [DONE]"])])
    assert "".join(client.call_stream("hi")) == "fallback-ok"
    assert len(calls) == 2
    assert calls[0]["enable_thinking"] is False
    assert "enable_thinking" not in calls[1]


def test_pure_reasoning_stream_is_failure_and_falls_to_next_model(monkeypatch):
    """v15 根因：整段只有 reasoning_content，旧实现会静默返回空串。"""
    qc, client, calls = _client(
        monkeypatch, ["model-thinking", "model-plain"],
        [_FakeResp(200, [_sse(reasoning="think...") for _ in range(3)] + ["data: [DONE]"]),
         _FakeResp(200, [_sse(content="real-code"), "data: [DONE]"])])
    assert "".join(client.call_stream("hi")) == "real-code"
    assert [c["model"] for c in calls] == ["model-thinking", "model-plain"]


def test_zero_content_all_models_yields_explicit_failure(monkeypatch):
    qc, client, calls = _client(
        monkeypatch, ["model-thinking"],
        [_FakeResp(200, [_sse(reasoning="think"), "data: [DONE]"])])
    out = "".join(client.call_stream("hi"))
    assert "[API 调用失败:" in out
    assert "零正文" in out


def test_first_content_timeout_switches_model(monkeypatch):
    qc, client, calls = _client(
        monkeypatch, ["slow", "fast"],
        [_FakeResp(200, [_sse(reasoning="think") for _ in range(20)]),
         _FakeResp(200, [_sse(content="fast-ok"), "data: [DONE]"])])
    monkeypatch.setattr(qc, "time", _FakeClock(step=1.0))
    monkeypatch.setattr(qc, "stream_first_content_sec", lambda: 2.0)
    monkeypatch.setattr(qc, "stream_wall_timeout_sec", lambda: 999.0)
    assert "".join(client.call_stream("hi")) == "fast-ok"
    assert [c["model"] for c in calls] == ["slow", "fast"]


def test_wall_timeout_after_partial_content_is_fail_closed(monkeypatch):
    """已有正文后超时：不得换模型重生成（会拼出损坏文件）。"""
    qc, client, calls = _client(
        monkeypatch, ["m1", "m2"],
        [_FakeResp(200, [_sse(content="partial"), _sse(content="more"),
                         _sse(content="even-more")])])
    monkeypatch.setattr(qc, "time", _FakeClock(step=2.0))
    monkeypatch.setattr(qc, "stream_first_content_sec", lambda: 999.0)
    monkeypatch.setattr(qc, "stream_wall_timeout_sec", lambda: 3.0)
    out = "".join(client.call_stream("hi"))
    assert "[API 调用失败:" in out
    assert "partial" in out
    assert [c["model"] for c in calls] == ["m1"], "绝不允许换模型续写"


def test_normal_multichunk_stream_unchanged(monkeypatch):
    qc, client, calls = _client(
        monkeypatch, ["qwen3.8-27b"],
        [_FakeResp(200, ["", ": ping", _sse(content="A"), _sse(content="B"),
                         "data: [DONE]"])])
    assert "".join(client.call_stream("hi")) == "AB"
    assert len(calls) == 1


def test_call_raises_on_failure_text(monkeypatch):
    """QwenClient.call() 对上游失败文本必须 FAIL-CLOSED。"""
    qc, client, calls = _client(
        monkeypatch, ["model-thinking"],
        [_FakeResp(200, [_sse(reasoning="think"), "data: [DONE]"])])
    with pytest.raises(RuntimeError):
        client.call("hi")
