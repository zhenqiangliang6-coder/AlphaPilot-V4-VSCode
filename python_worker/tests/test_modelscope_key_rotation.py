# -*- coding: utf-8 -*-
"""G10.28: ModelScope 多账号 key 轮换契约。

用户新增了 MODELSCOPE_API_KEY_A / _B 两个独立账号（实测 6 模型链全 200），
旧实现只读 MODELSCOPE_API_KEY，单账号魔粒耗尽就熔断整个 Provider，
把「一个账号没额度」误判成「平台不可用」。轮换只认 429 免费额度耗尽，
网络错误 / 5xx / 普通限流仍交既有路径策略与模型降级链。
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from python_worker.agents.qwen.providers import modelscope_client as msc  # noqa: E402


class _Resp:
    def __init__(self, status=200, text="", payload=None):
        self.status_code = status
        self.text = text
        self._payload = payload or {}
        self.closed = False

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def close(self):
        self.closed = True


def _client(monkeypatch, keys=("K0", "KA", "KB")):
    for name in msc._KEY_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name, val in zip(msc._KEY_ENV_NAMES, keys):
        if val is not None:
            monkeypatch.setenv(name, val)
    monkeypatch.setenv("MODELSCOPE_QUOTA_VERIFY", "0")
    monkeypatch.setenv("MODELSCOPE_PROXY_URL", "")
    return msc.ModelScopeClient()


def _quota_429():
    return _Resp(429, '{"error":{"message":"insufficient balance"}}')


def _ok():
    return _Resp(200, "ok", {"choices": [{"message": {"content": "OK"}}]})


# ── key 池解析 ────────────────────────────────────────────────────

def test_key_pool_is_deduped_and_ordered(monkeypatch):
    c = _client(monkeypatch, ("K0", "KA", "KA", "KB"))
    assert c._api_keys == ["K0", "KA", "KB"]
    assert c._api_key == "K0"
    assert c._key_index == 0


def test_single_key_pool(monkeypatch):
    c = _client(monkeypatch, ("ONLY",))
    assert c._api_keys == ["ONLY"]
    assert c._rotate_key() is False


def test_empty_pool_is_reported_as_unconfigured(monkeypatch):
    c = _client(monkeypatch, ())
    assert c._api_keys == []
    assert c._api_key == ""
    assert c._current_key() == ""


# ── _post 轮换行为 ────────────────────────────────────────────────

def test_quota_429_rotates_to_next_key(monkeypatch):
    c = _client(monkeypatch)
    seen = []
    responses = [_quota_429(), _ok()]

    def fake_post(_url, headers=None, **_kw):
        seen.append(headers["Authorization"])
        return responses.pop(0)

    monkeypatch.setattr(c._session, "post", fake_post)
    r = c._post("m", "p", 0.3, False, None)
    assert r.status_code == 200
    assert seen == ["Bearer K0", "Bearer KA"]
    assert c._key_index == 1
    assert c._current_key() == "KA"


def test_rotation_is_persistent_for_later_calls(monkeypatch):
    """切到 KA 后后续调用直接用 KA，不再每轮白撞一次 K0。"""
    c = _client(monkeypatch)
    seen = []

    def fake_post(_url, headers=None, **_kw):
        seen.append(headers["Authorization"])
        return _quota_429() if len(seen) == 1 else _ok()

    monkeypatch.setattr(c._session, "post", fake_post)
    assert c._post("m", "p", 0.3, False, None).status_code == 200
    assert c._post("m2", "p", 0.3, False, None).status_code == 200
    assert seen == ["Bearer K0", "Bearer KA", "Bearer KA"]


def test_all_keys_exhausted_returns_429_for_circuit(monkeypatch):
    """所有账号都耗尽 → 返回 429 交 provider_health 冷却，不无限重试。"""
    c = _client(monkeypatch)
    calls = []

    def fake_post(_url, headers=None, **_kw):
        calls.append(headers["Authorization"])
        return _quota_429()

    monkeypatch.setattr(c._session, "post", fake_post)
    r = c._post("m", "p", 0.3, False, None)
    assert r.status_code == 429
    assert calls == ["Bearer K0", "Bearer KA", "Bearer KB"]
    assert c._rotate_key() is False


def test_success_does_not_rotate(monkeypatch):
    c = _client(monkeypatch)
    monkeypatch.setattr(c._session, "post", lambda *_a, **_k: _ok())
    assert c._post("m", "p", 0.3, False, None).status_code == 200
    assert c._key_index == 0


def test_plain_rate_limit_does_not_rotate(monkeypatch):
    """普通 429 限流交给既有退避，不误切账号。"""
    c = _client(monkeypatch)
    monkeypatch.setattr(
        c._session, "post",
        lambda *_a, **_k: _Resp(429, '{"error":{"message":"rate limit"}}'),
    )
    assert c._post("m", "p", 0.3, False, None).status_code == 429
    assert c._key_index == 0


def test_server_error_does_not_rotate(monkeypatch):
    c = _client(monkeypatch)
    monkeypatch.setattr(c._session, "post", lambda *_a, **_k: _Resp(503, "bad gateway"))
    assert c._post("m", "p", 0.3, False, None).status_code == 503
    assert c._key_index == 0


# ── call() 集成：轮换后真正拿到内容 ───────────────────────────────

def test_call_returns_content_after_rotation(monkeypatch):
    c = _client(monkeypatch)
    responses = [_quota_429(), _ok()]

    def fake_post(_url, headers=None, **_kw):
        return responses.pop(0)

    monkeypatch.setattr(c._session, "post", fake_post)
    assert c.call("hi") == "OK"


def test_source_still_checks_key_before_call():
    src = Path(msc.__file__).read_text(encoding="utf-8")
    assert "if not self._api_key:" in src
    assert "_KEY_ENV_NAMES" in src
