# python_worker/tests/test_provider_chain.py
"""G10.55 有序多级 Provider 降级链契约（2026-11-18）。

v59 一遍 4 failed 的根因是「当日额度耗尽」而非代码回归：ModelScope 魔粒
429 耗尽、DashScope qwen3.7-max-preview 403 免费额度耗尽。此前 qwen_api
的跨 Provider 降级是硬编码一跳（任意 Provider → QwenClient），Qwen 也 403
时整条链直接断掉，没有后续兜底。

本文件锁死三件事：
1. 链序由 LLM_PROVIDER_CHAIN 控制，默认保持向后兼容（主链 → qwen）；
2. 降级按链序逐级推进，前一级失败才试下一级，绝不「每步白撞一次墙」；
3. 主链（modelscope）可成功时优先使用主链，不因存在备用 Provider 而跳链。
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker.agents.qwen import qwen_api  # noqa: E402


def _fail_client(name):
    class _Fail:
        def call_stream(self, prompt, temperature=0.3):
            yield f"\n\n[API 调用失败: {name} 不可用]"

        def call(self, prompt, temperature=0.3):
            raise RuntimeError(f"{name} 不可用")

    return _Fail()


def _ok_client(text="OK"):
    class _Ok:
        def call_stream(self, prompt, temperature=0.3):
            yield text

        def call(self, prompt, temperature=0.3):
            return text

    return _Ok()


def _patch_clients(monkeypatch, clients):
    monkeypatch.setattr(qwen_api, "_client_for", lambda p, primary: clients[p])


# ── 1. 链序解析 ──────────────────────────────────────────────

def test_chain_resolves_env_order(monkeypatch):
    monkeypatch.setenv(
        "LLM_PROVIDER_CHAIN", "modelscope,qwen,deepseek_maas,tencent_maas,volc_deepseek"
    )
    assert qwen_api._provider_chain() == [
        "modelscope", "qwen", "deepseek_maas", "tencent_maas", "volc_deepseek",
    ]


def test_chain_dedup_and_trim(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", " modelscope ,qwen, modelscope ")
    assert qwen_api._provider_chain() == ["modelscope", "qwen"]


def test_chain_default_backward_compatible(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER_CHAIN", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "modelscope")
    assert qwen_api._provider_chain() == ["modelscope", "qwen"]


# ── 2. 主链优先，成功后不跳链 ────────────────────────────────

def test_stream_uses_primary_first(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", "modelscope,qwen,deepseek_maas")
    _patch_clients(monkeypatch, {
        "modelscope": _ok_client("FROM_MODELSCOPE"),
        "qwen": _ok_client("SHOULD_NOT_APPEAR"),
        "deepseek_maas": _ok_client("SHOULD_NOT_APPEAR"),
    })
    out = "".join(qwen_api.call_llm_stream("hi"))
    assert out == "FROM_MODELSCOPE", out


def test_call_uses_primary_first(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", "modelscope,qwen")
    _patch_clients(monkeypatch, {
        "modelscope": _ok_client("MS"),
        "qwen": _ok_client("NO"),
    })
    assert qwen_api.call_llm("hi") == "MS"


# ── 3. 逐级降级，前一级失败才试下一级 ────────────────────────

def test_stream_degrades_through_chain(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", "modelscope,qwen,deepseek_maas")
    _patch_clients(monkeypatch, {
        "modelscope": _fail_client("modelscope"),
        "qwen": _fail_client("qwen"),
        "deepseek_maas": _ok_client("FROM_MAAS"),
    })
    out = "".join(qwen_api.call_llm_stream("hi"))
    assert out == "FROM_MAAS", out


def test_call_degrades_through_chain(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", "modelscope,qwen,deepseek_maas")
    _patch_clients(monkeypatch, {
        "modelscope": _fail_client("modelscope"),
        "qwen": _fail_client("qwen"),
        "deepseek_maas": _ok_client("FROM_MAAS"),
    })
    assert qwen_api.call_llm("hi") == "FROM_MAAS"


def test_all_providers_fail_returns_failure_text(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", "modelscope,qwen")
    _patch_clients(monkeypatch, {
        "modelscope": _fail_client("modelscope"),
        "qwen": _fail_client("qwen"),
    })
    out = "".join(qwen_api.call_llm_stream("hi"))
    assert "[API 调用失败" in out, out
    assert "modelscope" in out and "qwen" in out


def test_all_providers_fail_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", "modelscope,qwen")
    _patch_clients(monkeypatch, {
        "modelscope": _fail_client("modelscope"),
        "qwen": _fail_client("qwen"),
    })
    try:
        qwen_api.call_llm("hi")
    except RuntimeError as e:
        assert "所有 Provider 不可用" in str(e)
    else:
        raise AssertionError("应当抛出 RuntimeError")