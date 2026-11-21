# python_worker/tests/test_model_chain_probe_fallback_g1035.py
"""G10.35 配置优先链必须在配置失效时仍有活路。

shopflow_v14_1 实证（15:29，7 failed in 93.49s）：魔搭三个 key 全部 429
insufficient balance，DashScope 的 qwen3.6-plus / qwen3.5-plus / qwen-plus
全部 403「Free quota exhausted」，而运行时探测已验证 qwen3.8-27b 等 6 个
新代际模型可用(HTTP 200)。旧实现 `if chain: return chain[:4]` 只要 .env
配了 QWEN_MODEL 就永远不看探测结果 —— 「配置优先」变成「配置即死路」，
R5 直接 FAIL-CLOSED，一遍 7 个用例全挂。
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker.agents.qwen import qwen_model_probe as probe  # noqa: E402


def _setup(monkeypatch, env_chain, probe_chain):
    for key in ("QWEN_MODEL", "QWEN_FALLBACK_1", "QWEN_FALLBACK_2",
                "QWEN_FALLBACK_3", "QWEN_FAST_MODEL"):
        monkeypatch.delenv(key, raising=False)
    for i, m in enumerate(env_chain):
        monkeypatch.setenv("QWEN_MODEL" if i == 0 else f"QWEN_FALLBACK_{i}", m)
    monkeypatch.setattr(probe, "_use_fast_model", lambda: False)
    monkeypatch.setattr(probe, "probe_qwen_models",
                        lambda *a, **kw: {"text": list(probe_chain)})


def test_probe_models_are_appended_when_env_chain_is_dead(monkeypatch):
    """env 链是死模型时，已验证的探测模型必须进入降级链。"""
    _setup(monkeypatch, ["qwen3.6-plus"],
           ["qwen3.8-27b", "qwen3.8-2.4t-a95b", "qwen3.7-max-preview"])
    chain = probe.get_text_fallback_chain()
    assert chain[0] == "qwen3.6-plus", "配置优先顺序不变"
    assert "qwen3.8-27b" in chain
    assert "qwen3.8-2.4t-a95b" in chain
    assert "qwen3.7-max-preview" in chain


def test_append_is_deduplicated_ordered_and_bounded(monkeypatch):
    """追加去重、保序，且链长有上界，不会让每次调用白撞十几个模型。"""
    _setup(monkeypatch,
           ["m1", "m2", "m3", "m4"],
           ["m2", "m5", "m6", "m7", "m8"])
    chain = probe.get_text_fallback_chain()
    assert chain == ["m1", "m2", "m3", "m4", "m5", "m6"]
    assert len(chain) <= 6
    assert len(chain) == len(set(chain))


def test_probe_failure_never_breaks_env_chain(monkeypatch):
    """探测本身异常时保持原配置链，FAIL-OPEN 不因探测故障阻断调用。"""
    _setup(monkeypatch, ["m1", "m2"], [])
    monkeypatch.setattr(
        probe, "probe_qwen_models",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("probe down")))
    assert probe.get_text_fallback_chain() == ["m1", "m2"]


def test_fast_model_hint_still_takes_chain_head(monkeypatch):
    """G10.18 的样板步骤快模型语义不被本次改动破坏。"""
    _setup(monkeypatch, ["strong"], ["fast-probe"])
    monkeypatch.setenv("QWEN_FAST_MODEL", "fast-env")
    monkeypatch.setattr(probe, "_use_fast_model", lambda: True)
    chain = probe.get_text_fallback_chain()
    assert chain[0] == "fast-env"
    assert "strong" in chain


def test_no_env_chain_still_uses_probe_results(monkeypatch):
    """未配置 env 模型时，仍以探测链为准（既有语义不变）。"""
    for key in ("QWEN_MODEL", "QWEN_FALLBACK_1", "QWEN_FALLBACK_2",
                "QWEN_FALLBACK_3", "QWEN_FAST_MODEL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(probe, "_use_fast_model", lambda: False)
    monkeypatch.setattr(probe, "probe_qwen_models",
                        lambda *a, **kw: {"text": ["p1", "p2"],
                                          "all_chat": ["p1", "p2"]})
    assert probe.get_text_fallback_chain() == ["p1", "p2"]
