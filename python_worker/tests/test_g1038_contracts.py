# python_worker/tests/test_g1038_contracts.py
"""G10.38 长提示推理模型拖死任务的通用治理契约。

真实故障（shopflow_v17_1，2026-11-15 17:30–18:00）：R5–R9 连续五轮
四维全绿，R10 `refactor_service_layer` 轮询 1800s 超时，一遍
`2 failed, 5 passed in 3378.74s`。

实测证据（同日 18:0x，3000+ 字符长 prompt 直连 DashScope 流式）：
- `qwen3.8-27b`      HTTP 403 Free quota exhausted（免费额度耗尽，非欠费）。
- `qwen3.8-2.4t-a95b` 65s 零正文 / 10478 字符 reasoning_content；
  关思考参数被 400 拒（restricted to True）。
- `qwen3.7-max-preview` 19.9s 首正文 / 26.0s / 3129 字符（可用但慢）。
- `deepseek-v4.1-flash` + enable_thinking=False：0.9s 首正文 / 4.4s /
  3430 字符 / 零推理链；分类请求 1.0s 返回干净 JSON。

v17 Worker 日志里 `qwen3.8-2.4t-a95b` 在 10 个步骤各被重试一次、
每次白等 90s 首正文上界，累计 1080s；`qwen3.8-27b` 每 300s
「冷却到期 → 立刻又 403」反复抖动。两者共同烧满 1800s 轮询窗口。

契约：零正文/墙钟超时的模型按 TTL 摘出候选链（一次判死，不再逐步重试）；
连续额度耗尽指数退避；成功产出即清失败计数；关思考白名单与首正文
上界按实测更新；主链按实测时延排序。
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
    for name in ("QWEN_NO_THINK_MODELS", "QWEN_STREAM_WALL_TIMEOUT_SEC",
                 "QWEN_STREAM_FIRST_CONTENT_SEC", "QWEN_QUOTA_COOLDOWN_SEC",
                 "QWEN_STREAM_FAIL_COOLDOWN_SEC"):
        monkeypatch.delenv(name, raising=False)
    qwen_client.reset_exhausted_models()
    return qwen_client


class _FakeResp:
    def __init__(self, status=200, lines=None, text=""):
        self.status_code = status
        self._lines = lines or []
        self.text = text
        self.encoding = None
        self.closed = False

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


def _ok(content="ok"):
    return _FakeResp(200, [_sse(content=content), "data: [DONE]"])


def _client(monkeypatch, models, response_factory):
    """response_factory(model, index) -> FakeResp；记录每次请求的 body。"""
    qc = _qc(monkeypatch)
    client = qc.QwenClient()
    monkeypatch.setattr(client, "_get_chain", lambda: list(models))
    calls = []
    counter = {"n": 0}

    def post(url, **kw):
        calls.append(kw["json"])
        idx = counter["n"]
        counter["n"] += 1
        return response_factory(kw["json"]["model"], idx)

    monkeypatch.setattr(client._session, "post", post)
    return qc, client, calls


# ---------------------------------------------------------------- 纯函数契约

def test_no_think_default_includes_fast_non_reasoning_model(monkeypatch):
    qc = _qc(monkeypatch)
    assert qc.wants_no_thinking("deepseek-v4.1-flash")
    assert qc.wants_no_thinking("qwen3.8-27b")
    assert not qc.wants_no_thinking("qwen3.8-2.4t-a95b")
    assert not qc.wants_no_thinking("qwen3.7-max-preview")


def test_first_content_default_is_45s(monkeypatch):
    qc = _qc(monkeypatch)
    assert qc.stream_first_content_sec() == 45.0
    assert qc.stream_wall_timeout_sec() == 240.0
    monkeypatch.setenv("QWEN_STREAM_FIRST_CONTENT_SEC", "12")
    assert qc.stream_first_content_sec() == 12.0


def test_stream_fail_cooldown_api(monkeypatch):
    qc = _qc(monkeypatch)
    assert qc.stream_fail_cooldown_sec() == 600.0
    assert not qc.is_stream_cooling("m")
    qc.mark_stream_failure("m")
    assert qc.is_stream_cooling("m")
    assert qc.stream_failing_models() == {"m"}
    assert qc.exhausted_models() == set(), "额度冷却与流式失败冷却必须互不污染"
    qc.reset_exhausted_models()
    assert not qc.is_stream_cooling("m")
    assert qc.stream_failing_models() == set()


def test_stream_fail_cooldown_expires(monkeypatch):
    qc = _qc(monkeypatch)
    clock = {"t": 100.0}
    monkeypatch.setattr(qc.time, "monotonic", lambda: clock["t"])
    monkeypatch.setenv("QWEN_STREAM_FAIL_COOLDOWN_SEC", "10")
    qc.mark_stream_failure("m")
    assert qc.is_stream_cooling("m")
    clock["t"] = 109.0
    assert qc.is_stream_cooling("m")
    clock["t"] = 111.0
    assert not qc.is_stream_cooling("m"), "到期必须半开重试，不是永久拉黑"
    assert "m" not in qc.stream_failing_models()


def test_quota_cooldown_backs_off_on_repeated_exhaustion(monkeypatch):
    """v17 抖动：每 300s 到期立刻又 403，反复刷屏。"""
    qc = _qc(monkeypatch)
    assert qc.quota_cooldown_sec("m") == 300.0
    qc._mark_model_exhausted("m")
    assert qc.quota_cooldown_sec("m") == 300.0
    qc._mark_model_exhausted("m")
    assert qc.quota_cooldown_sec("m") == 600.0
    qc._mark_model_exhausted("m")
    assert qc.quota_cooldown_sec("m") == 1200.0
    for _ in range(10):
        qc._mark_model_exhausted("m")
    assert qc.quota_cooldown_sec("m") == 3600.0, "退避必须有上限"
    assert "m" in qc.exhausted_models()
    qc.reset_exhausted_models()
    assert qc.quota_cooldown_sec("m") == 300.0


def test_success_clears_failure_state(monkeypatch):
    qc = _qc(monkeypatch)
    qc.mark_stream_failure("m")
    qc._mark_model_exhausted("m")
    qc._mark_stream_success("m")
    assert not qc.is_stream_cooling("m")
    assert qc.quota_cooldown_sec("m") == 300.0


# ---------------------------------------------------------------- 集成契约

def test_zero_content_model_is_cooled_after_first_failure(monkeypatch):
    """核心回归：v17 里慢模型被 10 个步骤各调用一次，每次白等首正文上界。

    现在第一次零正文就摘出候选链，后续 9 个步骤直接命中可用模型。
    """
    models = ["slow-thinker", "fast-plain"]

    def factory(model, idx):
        if model == "slow-thinker":
            return _FakeResp(200, [_sse(reasoning="think") for _ in range(3)] + ["data: [DONE]"])
        return _ok("code")

    qc, client, calls = _client(monkeypatch, models, factory)
    for _ in range(10):
        assert "".join(client.call_stream("long prompt")) == "code"

    requested = [c["model"] for c in calls]
    assert requested.count("slow-thinker") == 1, requested
    assert requested.count("fast-plain") == 10
    assert qc.is_stream_cooling("slow-thinker")
    assert "slow-thinker" not in qc.exhausted_models()


def test_first_content_timeout_also_cools_model(monkeypatch):
    clock = {"t": 0.0}

    def factory(model, idx):
        if model == "slow":
            return _FakeResp(200, [_sse(reasoning="think") for _ in range(20)])
        return _ok("fast-ok")

    qc, client, calls = _client(monkeypatch, ["slow", "fast"], factory)
    monkeypatch.setattr(qc.time, "monotonic", lambda: clock.__setitem__("t", clock["t"] + 1.0) or clock["t"])
    monkeypatch.setattr(qc, "stream_first_content_sec", lambda: 2.0)
    monkeypatch.setattr(qc, "stream_wall_timeout_sec", lambda: 999.0)
    assert "".join(client.call_stream("hi")) == "fast-ok"
    assert qc.is_stream_cooling("slow")
    assert "".join(client.call_stream("hi again")) == "fast-ok"
    assert [c["model"] for c in calls] == ["slow", "fast", "fast"]


def test_all_models_stream_cooling_yields_explicit_failure(monkeypatch):
    qc = _qc(monkeypatch)
    qc.mark_stream_failure("only")
    client = qc.QwenClient()
    monkeypatch.setattr(client, "_get_chain", lambda: ["only"])
    monkeypatch.setattr(client._session, "post", lambda *a, **k: pytest.fail("不应发起请求"))
    out = "".join(client.call_stream("hi"))
    assert "[API 调用失败:" in out
    assert "流式失败冷却" in out


def test_403_exhausted_model_is_cooled_and_falls_back(monkeypatch):
    qc = _qc(monkeypatch)

    def factory(model, idx):
        if model == "exhausted":
            return _FakeResp(403, text='{"error":{"message":"Free quota exhausted"}}')
        return _ok("fallback-code")

    _, client, calls = _client(monkeypatch, ["exhausted", "healthy"], factory)
    assert "".join(client.call_stream("hi")) == "fallback-code"
    assert qc.exhausted_models() == {"exhausted"}
    assert "".join(client.call_stream("hi again")) == "fallback-code"
    assert [c["model"] for c in calls] == ["exhausted", "healthy", "healthy"]


def test_primary_model_sends_no_think_param(monkeypatch):
    """G10.38 主链 deepseek-v4.1-flash 必须拿到关思考参数。"""
    _, client, calls = _client(
        monkeypatch, ["deepseek-v4.1-flash"], lambda m, i: _ok("code"))
    assert "".join(client.call_stream("write code")) == "code"
    assert calls[0]["model"] == "deepseek-v4.1-flash"
    assert calls[0]["enable_thinking"] is False
