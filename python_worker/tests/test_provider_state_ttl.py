# python_worker/tests/test_provider_state_ttl.py
"""G10.29 长驻进程状态自愈回归契约。

v8 第 1 遍真实故障（2026-11-15 12:16–12:35）：
  - R5 期间 api-inference.modelscope.cn 出现瞬时 DNS 解析失败（11001），
    主链 6 个模型全挂，跨 Provider 降级到 DashScope；
  - DashScope 三个模型在此前某次 403 后被「本进程永久拉黑」，于是整条
    候选链被跳过，直接吐出失败文本；
  - 11 分钟后的 R9 重复同一路径，即使 DNS 已恢复、魔搭额度已领取，
    仍因进程内旧状态被判失败，最终 4 failed / 3 passed。

本文件锁死三处修复：
1. Qwen 模型额度熔断改为带 TTL 冷却，到期自动半开；
2. ModelScope 代理熔断改为带 TTL 冷却，到期自动半开；
3. 主链网络型失败在跨 Provider 降级前重试一次，额度型失败不重试。
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))


class _FakeResp:
    def __init__(self, status=200, text="{}"):
        self.status_code = status
        self.text = text
        self.encoding = None

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_lines(self, decode_unicode=True):
        return iter([])


def _make_qwen_client(monkeypatch):
    from python_worker.agents.qwen.providers import qwen_client
    import python_worker.worker_config as wc
    monkeypatch.setattr(wc, "DASHSCOPE_API_KEY", "dummy-key")
    client = qwen_client.QwenClient()
    monkeypatch.setattr(client, "_get_chain", lambda: ["m-a", "m-b"])
    return client, qwen_client


# ── 1. Qwen 模型额度冷却 TTL ────────────────────────────────────

def test_quota_cooldown_default_keeps_model_out(monkeypatch):
    """默认 300s 冷却：刚标记的模型不参与本次候选链（保留旧契约）。"""
    client, qc = _make_qwen_client(monkeypatch)
    qc.reset_exhausted_models()
    monkeypatch.delenv("QWEN_QUOTA_COOLDOWN_SEC", raising=False)
    qc._mark_model_exhausted("m-a")
    assert "m-a" in qc.exhausted_models()
    assert qc._quota_cooldown_sec() == 300.0

    calls = []

    def post(url, **kw):
        calls.append(kw["json"]["model"])
        return _FakeResp()

    monkeypatch.setattr(client._session, "post", post)
    list(client.call_stream("hi"))
    assert calls == ["m-b"], calls
    qc.reset_exhausted_models()


def test_quota_cooldown_expiry_reopens_model(monkeypatch):
    """冷却到期后自动半开：模型重新进入候选链，无需重启 Worker。"""
    client, qc = _make_qwen_client(monkeypatch)
    qc.reset_exhausted_models()
    qc._mark_model_exhausted("m-a")
    monkeypatch.setenv("QWEN_QUOTA_COOLDOWN_SEC", "0")
    assert "m-a" not in qc.exhausted_models()

    calls = []

    def post(url, **kw):
        calls.append(kw["json"]["model"])
        return _FakeResp()

    monkeypatch.setattr(client._session, "post", post)
    list(client.call_stream("hi"))
    assert calls[0] == "m-a", calls
    qc.reset_exhausted_models()


def test_quota_cooldown_invalid_env_falls_back(monkeypatch):
    """非法环境变量不能把冷却变成 0（净加严，避免误放行）。"""
    from python_worker.agents.qwen.providers import qwen_client
    monkeypatch.setenv("QWEN_QUOTA_COOLDOWN_SEC", "not-a-number")
    assert qwen_client._quota_cooldown_sec() == 300.0


# ── 2. ModelScope 代理熔断 TTL ─────────────────────────────────

def test_proxy_circuit_opens_within_cooldown(monkeypatch):
    from python_worker.agents.qwen.providers import modelscope_client as mc
    monkeypatch.setattr(mc, "_PROXY_CIRCUIT_OPENED_AT", None)
    monkeypatch.delenv("MODELSCOPE_PROXY_COOLDOWN_SEC", raising=False)
    mc._open_proxy_circuit()
    assert mc._proxy_circuit_open() is True
    monkeypatch.setattr(mc, "_PROXY_CIRCUIT_OPENED_AT", None)


def test_proxy_circuit_reopens_after_cooldown(monkeypatch):
    from python_worker.agents.qwen.providers import modelscope_client as mc
    monkeypatch.setenv("MODELSCOPE_PROXY_COOLDOWN_SEC", "0")
    mc._open_proxy_circuit()
    assert mc._proxy_circuit_open() is False
    assert mc._PROXY_CIRCUIT_OPENED_AT is None


# ── 3. 主链网络型失败重试一次 ──────────────────────────────────

def test_network_failure_marker_detection():
    from python_worker.agents.qwen import qwen_api
    assert qwen_api._is_transient_network_failure(
        "[API 调用失败: 所有 ModelScope 模型不可用 - "
        "NameResolutionError ... getaddrinfo failed]"
    )
    assert not qwen_api._is_transient_network_failure(
        "[API 调用失败: 候选链模型免费额度均已耗尽(403)，请领取额度或切换 Provider]"
    )
    assert not qwen_api._is_transient_network_failure("正常生成的代码文本")


class _FakeMainClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def call_stream(self, prompt, temperature=0.3):
        self.calls += 1
        yield self.outcomes.pop(0)


class _FakeFallback:
    def call_stream(self, prompt, temperature=0.3):
        yield "FALLBACK"


def _patch_stream_env(monkeypatch, client):
    from python_worker.agents.qwen import qwen_api
    from python_worker.agents.qwen.providers import qwen_client as qc_mod
    monkeypatch.setenv("LLM_PROVIDER", "modelscope")
    monkeypatch.setattr(qwen_api, "_get_client", lambda: client)
    monkeypatch.setattr(qwen_api.time, "sleep", lambda _: None)
    monkeypatch.setattr(qc_mod, "QwenClient", lambda: _FakeFallback())
    return qwen_api


def test_network_failure_retries_main_chain_once(monkeypatch):
    """DNS 抖动重试成功 → 不降级、不产出失败文本。"""
    client = _FakeMainClient([
        "\n\n[API 调用失败: 所有 ModelScope 模型不可用 - NameResolutionError getaddrinfo failed]",
        "OK",
    ])
    qwen_api = _patch_stream_env(monkeypatch, client)
    out = "".join(qwen_api.call_llm_stream("hi"))
    assert out == "OK", out
    assert client.calls == 2
    assert "FALLBACK" not in out


def test_network_failure_still_fails_falls_back(monkeypatch):
    """重试仍失败 → 仍执行跨 Provider 降级，不吞掉失败。"""
    fail = "\n\n[API 调用失败: 所有 ModelScope 模型不可用 - ConnectionError]"
    client = _FakeMainClient([fail, fail])
    qwen_api = _patch_stream_env(monkeypatch, client)
    out = "".join(qwen_api.call_llm_stream("hi"))
    assert "FALLBACK" in out, out
    assert client.calls == 2


def test_quota_failure_does_not_retry(monkeypatch):
    """额度型失败立即降级，不额外等待、不改变 FAIL-CLOSED 语义。"""
    client = _FakeMainClient([
        "\n\n[API 调用失败: 候选链模型免费额度均已耗尽(403)，请领取额度或切换 Provider]"
    ])
    qwen_api = _patch_stream_env(monkeypatch, client)
    out = "".join(qwen_api.call_llm_stream("hi"))
    assert "FALLBACK" in out, out
    assert client.calls == 1
