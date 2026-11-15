# -*- coding: utf-8 -*-
"""Provider 健康状态回归契约（2026-11-14 事后纠错版）。

真实故障：ModelScope 免费魔粒额度耗尽后，主模型 + 5 个降级模型全部返回
`429 insufficient balance`。旧实现误判成「账户欠费、不可恢复」，永久熔断
整个 Provider，把主线从 ModelScope 切走且再不回头。

官方文档核查后的正确语义：
  * ModelScope API-Inference **免费**，无充值入口，用「魔粒」积分抵扣；
    `insufficient balance` = 当日免费额度不足（每日 0 点 UTC+8 重置），
    或突发限流被误报成该文案 —— **两者都可恢复**。
  * 因此 429 balance → 带 TTL 的冷却 + 到期自动半开；
    401/402/403 quota → 真不可恢复，永久熔断；
    普通 429 限流 → 不熔断，交给退避。
  * 冷却期间整链（主调用 / 流式 / 意图分类 / 规划器）立刻切备用上游，
    且停止遍历 6 个降级模型（换模型无意义、还会放大限流）。
"""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker import provider_health  # noqa: E402
from python_worker.agents.qwen.providers.modelscope_client import (  # noqa: E402
    ModelScopeClient,
    _maybe_trip_account_circuit,
)


@pytest.fixture(autouse=True)
def _clean_circuit():
    provider_health.reset()
    yield
    provider_health.reset()


class _FakeResponse:
    def __init__(self, status, text=""):
        self.status_code = status
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return {}


def test_trip_is_idempotent_and_resettable():
    assert not provider_health.is_open("modelscope")
    provider_health.trip("modelscope", "reason-1")
    provider_health.trip("modelscope", "reason-2")
    assert provider_health.is_open("modelscope")
    assert provider_health.reason("modelscope") == "reason-1"
    assert "modelscope" in provider_health.snapshot()
    provider_health.reset("modelscope")
    assert not provider_health.is_open("modelscope")


def test_balance_429_is_recoverable_quota_cooldown():
    """429 balance 是当日免费额度耗尽/限流误报，只能冷却，不能永久熔断。"""
    _maybe_trip_account_circuit(
        _FakeResponse(429, '{"error":{"message":"insufficient balance"}}')
    )
    assert provider_health.is_open("modelscope")
    assert "insufficient balance" in provider_health.reason("modelscope")
    assert provider_health.kind("modelscope") == provider_health.QUOTA
    assert provider_health.cooldown_remaining("modelscope") > 0


def test_quota_cooldown_expires_and_half_opens_automatically():
    """冷却到期后自动半开，无需重启 Worker、无需人工 reset。"""
    provider_health.trip_quota("modelscope", "429 insufficient balance", ttl=0.05)
    assert provider_health.is_open("modelscope")
    import time
    time.sleep(0.08)
    assert not provider_health.is_open("modelscope"), "冷却到期应自动恢复"
    assert provider_health.reason("modelscope") == ""
    assert provider_health.kind("modelscope") == ""


def test_fatal_cannot_be_diluted_by_quota():
    """真鉴权失效优先级最高，不能被后续 quota 信号降级成短冷却。"""
    provider_health.trip("modelscope", "401 Authentication failed",
                         kind=provider_health.FATAL)
    provider_health.trip_quota("modelscope", "429 insufficient balance")
    assert provider_health.kind("modelscope") == provider_health.FATAL
    assert provider_health.cooldown_remaining("modelscope") == 0.0


def test_classify_response_distinguishes_fatal_quota_and_transient():
    from python_worker.provider_health import classify_response, FATAL, QUOTA
    assert classify_response(
        _FakeResponse(401, "Authentication failed"))[0] == FATAL
    assert classify_response(
        _FakeResponse(403, "quota exceeded"))[0] == FATAL
    assert classify_response(
        _FakeResponse(429, '{"error":{"message":"insufficient balance"}}'))[0] == QUOTA
    assert classify_response(
        _FakeResponse(429, "rate limit exceeded, retry later"))[0] is None
    assert classify_response(_FakeResponse(200, "ok"))[0] is None


@pytest.mark.parametrize("status,body", [
    (401, "Authentication failed"),
    (402, "payment required"),
    (403, "quota exceeded"),
])
def test_auth_and_payment_failures_trip_circuit(status, body):
    _maybe_trip_account_circuit(_FakeResponse(status, body))
    assert provider_health.is_open("modelscope")


def test_transient_rate_limit_does_not_trip_circuit():
    _maybe_trip_account_circuit(_FakeResponse(429, "rate limit exceeded, retry later"))
    assert not provider_health.is_open("modelscope")


def test_qwen_retry_budget_is_bounded():
    """可选 doc 步骤曾靠 3 次重试 × 4 模型烧掉 1079 秒，必须锁死上界。

    G10.20：为扛住上游网络瞬断把单次重试从 1 提到 2，但**总退避时间**
    仍必须硬上界（<= 10s），防止重试预算重新膨胀成分钟级拖尾。
    """
    from python_worker.agents.qwen.providers import qwen_client

    assert 1 <= qwen_client._NETWORK_RETRY_MAX <= 2
    assert len(qwen_client._NETWORK_RETRY_DELAYS) >= qwen_client._NETWORK_RETRY_MAX
    assert sum(qwen_client._NETWORK_RETRY_DELAYS) <= 10
    assert qwen_client._HTTP_TIMEOUT[1] <= 45


def test_qwen_fallback_client_bypasses_env_proxy(monkeypatch):
    """主链熔断后的兜底客户端不能再被宿主环境代理拖死。"""
    from python_worker.agents.qwen.providers.qwen_client import QwenClient

    client = QwenClient()
    assert client._session.trust_env is False
    monkeypatch.setattr(client, "_get_chain", lambda: ["probe-model"])

    class _OkStreamResponse:
        status_code = 200
        encoding = "utf-8"

        def raise_for_status(self):
            pass

        def iter_lines(self, decode_unicode=True):
            yield 'data: {"choices":[{"delta":{"content":"OK"}}]}'
            yield "data: [DONE]"

    seen = {}

    def fake_post(url, **kwargs):
        seen.update(kwargs)
        return _OkStreamResponse()

    monkeypatch.setattr(client._session, "post", fake_post)
    assert client.call("hi") == "OK"
    assert seen.get("proxies") == {}


def test_fatal_reason_helper():
    from python_worker.provider_health import fatal_reason

    assert fatal_reason(
        _FakeResponse(429, '{"error":{"message":"insufficient balance"}}')
    )
    assert fatal_reason(_FakeResponse(401, "Authentication failed"))
    assert fatal_reason(_FakeResponse(429, "rate limit exceeded")) is None
    assert fatal_reason(_FakeResponse(200, "ok")) is None


def test_classifier_skips_request_when_circuit_open(monkeypatch):
    import requests
    from python_worker.intent_router import _classification

    provider_health.trip("modelscope", "HTTP 429: insufficient balance")

    def explode():
        raise AssertionError("熔断后分类不应再发请求")

    monkeypatch.setattr(requests, "Session", explode)
    assert _classification.call_provider_for_classify("hi", "modelscope") == ""


def test_client_aborts_chain_on_balance_failure(monkeypatch):
    """额度耗尽时不能把 6 个降级模型挨个撞一遍（会放大限流）。"""
    monkeypatch.setenv("MODELSCOPE_API_KEY", "dummy")
    monkeypatch.setenv("MODELSCOPE_QUOTA_VERIFY", "0")  # 本契约聚焦降级链，不测误报复试
    for i in range(1, 6):
        monkeypatch.setenv(f"MODELSCOPE_FALLBACK_{i}", f"fake/model-{i}")
    monkeypatch.setenv("MODELSCOPE_MODEL", "fake/model-0")

    calls = []

    def fake_post(self, model, prompt, temperature, stream, proxies):
        calls.append(model)
        return _FakeResponse(429, '{"error":{"message":"insufficient balance"}}')

    monkeypatch.setattr(ModelScopeClient, "_post", fake_post)
    client = ModelScopeClient()
    with pytest.raises(RuntimeError):
        client.call("hello")

    assert calls == ["fake/model-0"], calls
    assert provider_health.is_open("modelscope")


def test_open_circuit_short_circuits_before_any_request(monkeypatch):
    monkeypatch.setenv("MODELSCOPE_API_KEY", "dummy")
    provider_health.trip("modelscope", "HTTP 429: insufficient balance")

    def explode(*a, **k):
        raise AssertionError("熔断后不应再发任何请求")

    monkeypatch.setattr(ModelScopeClient, "_post", explode)
    client = ModelScopeClient()
    with pytest.raises(RuntimeError, match="暂时不可用"):
        client.call("hello")
    out = "".join(client.call_stream("hello"))
    assert "API 调用失败" in out


def test_transient_quota_429_self_heals_without_tripping(monkeypatch):
    """限流误报：退避重试后成功 → 不熔断、不换模型、结果正常返回。"""
    monkeypatch.setenv("MODELSCOPE_API_KEY", "dummy")
    monkeypatch.setenv("MODELSCOPE_QUOTA_VERIFY", "1")
    monkeypatch.setenv("MODELSCOPE_MODEL", "fake/model-0")
    for i in range(1, 6):
        monkeypatch.delenv(f"MODELSCOPE_FALLBACK_{i}", raising=False)

    import python_worker.agents.qwen.providers.modelscope_client as ms

    class _Ok:
        status_code = 200
        text = "{}"

        def raise_for_status(self):
            pass

        def close(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "RECOVERED"}}]}

    calls = []

    def fake_post(self, model, prompt, temperature, stream, proxies):
        calls.append(model)
        if len(calls) == 1:
            return _FakeResponse(429, '{"error":{"message":"insufficient balance"}}')
        return _Ok()

    monkeypatch.setattr(ModelScopeClient, "_post", fake_post)
    monkeypatch.setattr(ms.time, "sleep", lambda _s: None)
    client = ModelScopeClient()
    assert client.call("hello") == "RECOVERED"
    # 同模型重试 1 次（不遍历降级链），第二次成功即自愈
    assert calls == ["fake/model-0", "fake/model-0"], calls
    assert not provider_health.is_open("modelscope"), "误报自愈后不应留下冷却"


def test_classifier_chain_cache_is_invalidated_by_circuit(monkeypatch):
    """熔断前缓存的魔搭模型链，熔断后必须失效，不能拿去打 DashScope。"""
    import types
    from python_worker.intent_router import _classification

    monkeypatch.setenv("LLM_PROVIDER", "modelscope")
    monkeypatch.setenv("MODELSCOPE_MODEL", "Qwen/Qwen3.8-Flash-Next")
    monkeypatch.delenv("INTENT_CLASSIFY_MODEL", raising=False)
    monkeypatch.setattr(_classification, "_CHAIN_CACHE", None)
    monkeypatch.setattr(_classification, "_CHAIN_CACHE_TS", 0)

    before = _classification._resolve_qwen_classify_chain()
    assert before[0] == "Qwen/Qwen3.8-Flash-Next"

    provider_health.trip("modelscope", "HTTP 429: insufficient balance")
    fake_probe = types.ModuleType("python_worker.agents.qwen.qwen_model_probe")
    fake_probe.probe_qwen_models = lambda: {"text": ["qwen-probe-1"]}
    monkeypatch.setitem(sys.modules, fake_probe.__name__, fake_probe)

    after = _classification._resolve_qwen_classify_chain()
    assert after == ["qwen-probe-1"], after


def test_planner_and_classifier_honor_circuit(monkeypatch):
    import types
    from python_worker import planner
    from python_worker.intent_router import _classification

    monkeypatch.setenv("LLM_PROVIDER", "modelscope")
    monkeypatch.delenv("INTENT_CLASSIFY_MODEL", raising=False)
    provider_health.trip("modelscope", "HTTP 429: insufficient balance")

    url, model, key, is_ms = planner._planner_endpoint()
    assert "dashscope" in url
    assert is_ms is False

    # 用假的探针模块隔离网络；熔断后分类链应走 DashScope 探测而非 ModelScope 固定链
    fake_probe = types.ModuleType("python_worker.agents.qwen.qwen_model_probe")
    fake_probe.probe_qwen_models = lambda: {"text": ["qwen-probe-1"]}
    monkeypatch.setitem(sys.modules, fake_probe.__name__, fake_probe)
    monkeypatch.setattr(_classification, "_CHAIN_CACHE", None)
    monkeypatch.setattr(_classification, "_CHAIN_CACHE_TS", 0)

    chain = _classification._resolve_qwen_classify_chain()
    assert chain == ["qwen-probe-1"], chain
    assert not any(m == "Qwen/Qwen3.8-Flash-Next" for m in chain)


# ── G10.23：INTENT_CLASSIFY_MODEL 不得成为分类器的单点故障 ────────────
# 取证（shopflow_v4_1 / R9）：qwen-plus 免费额度耗尽(403)，旧实现直接
# return [env_model]，分类器没有第二个模型可试 → 降级 Regex 把明确的枚举
# 级联修改题判成 chat → 零 FileOps、无授权记录、质量+治理双红并连锁 R10。

def _setup_classifier_env(monkeypatch, preferred, probe_text):
    import types
    from python_worker.intent_router import _classification

    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv("INTENT_CLASSIFY_MODEL", preferred)
    monkeypatch.setenv("QWEN_MODEL", "qwen3.6-plus")
    monkeypatch.setenv("QWEN_FALLBACK_1", "qwen3.5-plus")
    for key in ("QWEN_FAST_MODEL", "QWEN_FALLBACK_2", "QWEN_FALLBACK_3"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(_classification, "_CHAIN_CACHE", None)
    monkeypatch.setattr(_classification, "_CHAIN_CACHE_TS", 0)
    fake = types.ModuleType("python_worker.agents.qwen.qwen_model_probe")
    fake.probe_qwen_models = lambda: {"text": probe_text, "best_text": ""}
    monkeypatch.setitem(sys.modules, fake.__name__, fake)
    return _classification


def test_explicit_classify_model_is_chain_head_not_single_point(monkeypatch):
    """显式配置只做链首，其后必须有探测链 + 主执行链候选，且无重复。"""
    cls_mod = _setup_classifier_env(monkeypatch, "qwen-plus", ["qwen-probe-1"])
    chain = cls_mod._resolve_qwen_classify_chain()
    assert chain[0] == "qwen-plus", chain
    assert "qwen3.5-plus" in chain, chain       # 当时唯一可用模型
    assert "qwen-probe-1" in chain, chain
    assert len(chain) >= 3 and len(chain) == len(set(chain)), chain


def test_classifier_falls_back_after_preferred_model_quota_error(monkeypatch):
    """链首 403 后必须继续尝试下一个模型，不能整体降级 Regex。"""
    cls_mod = _setup_classifier_env(monkeypatch, "qwen-plus", [])
    tried = []

    def fake_call(prompt, model_name, model_override=None, max_timeout=60):
        tried.append(model_override)
        if model_override in ("qwen-plus", "qwen3.6-plus"):
            raise RuntimeError("HTTP 403: Free quota exhausted")
        return '{"intent":"write_code","target_type":"code","confidence":0.9}'

    monkeypatch.setattr(cls_mod, "call_provider_for_classify", fake_call)
    result = cls_mod.llm_classify("修改订单状态枚举值并更新所有引用", "qwen")
    assert result and result["intent"] == "write_code", result
    assert tried[0] == "qwen-plus", tried
    assert tried[-1] == "qwen3.5-plus", tried


def test_classifier_cache_invalidates_when_preferred_model_changes(monkeypatch):
    """首选模型热变更后，1 小时缓存不能继续返回旧链首。"""
    cls_mod = _setup_classifier_env(monkeypatch, "qwen-plus", ["qwen-probe-1"])
    first = cls_mod._resolve_qwen_classify_chain()
    assert first[0] == "qwen-plus"
    monkeypatch.setenv("INTENT_CLASSIFY_MODEL", "qwen3.5-plus")
    second = cls_mod._resolve_qwen_classify_chain()
    assert second[0] == "qwen3.5-plus", second
    assert second.count("qwen3.5-plus") == 1, second
