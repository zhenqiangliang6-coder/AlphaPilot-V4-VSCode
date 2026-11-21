# python_worker/tests/test_g1052_modelscope_wall_timeout.py
"""G10.52 ModelScope 非流式调用墙钟保护契约。

真实故障（shopflow_v55，2026-11-18 10:23-10:30）：ModelScope 主链从 429
恢复 200 后，R7 fix_code 阶段走 modelscope_client.call() 非流式长 prompt，
服务端保持连接活跃却迟迟不给完整 body，requests read timeout(180s) 在
「持续吐 reasoning/保活字节」时不触发，任务 hang 死、pytest rc=127。

对比 qwen_client.call() 早已改走 call_stream 拼接并带首正文/全程墙钟
（G10.36），ModelScope 恢复后成为唯一无墙钟治理的客户端。本契约锁定：
  1. ModelScope 与 Qwen 共用同一组墙钟环境变量口径；
  2. call() 走流式拼接（复用 _post 的 429 key 轮换/代理路径语义不变）；
  3. 失败文本与空内容 FAIL-CLOSED（抛 RuntimeError，交回 call_llm 降级链）。
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from python_worker.agents.qwen.providers import modelscope_client as mc
from python_worker.agents.qwen.providers import qwen_client as qc


def test_wall_timeout_shares_env_contract(monkeypatch):
    """墙钟口径与 qwen_client 一致：同一组环境变量读同样的值。"""
    monkeypatch.setenv("QWEN_STREAM_WALL_TIMEOUT_SEC", "33")
    monkeypatch.setenv("QWEN_STREAM_FIRST_CONTENT_SEC", "7")
    assert mc.stream_wall_timeout_sec() == qc.stream_wall_timeout_sec() == 33.0
    assert mc.stream_first_content_sec() == qc.stream_first_content_sec() == 7.0


def test_wall_timeout_env_lower_bound(monkeypatch):
    """非法/过小值收敛到 >=1s，绝不关闭墙钟（FAIL-CLOSED）。"""
    monkeypatch.setenv("QWEN_STREAM_WALL_TIMEOUT_SEC", "0")
    monkeypatch.setenv("QWEN_STREAM_FIRST_CONTENT_SEC", "garbage")
    assert mc.stream_wall_timeout_sec() >= 1.0
    assert mc.stream_first_content_sec() >= 1.0


def test_stream_one_enforces_wall_clock(monkeypatch):
    """iter_lines 之间推进墙钟，超首正文上界即抛 TimeoutError。"""
    client = mc.ModelScopeClient()

    class _Resp:
        status_code = 200
        encoding = None

        def raise_for_status(self):
            pass

        def iter_lines(self, decode_unicode=False):
            # 永不吐正文的保活流
            while True:
                yield b": keepalive"

        def close(self):
            pass

    monkeypatch.setenv("QWEN_STREAM_FIRST_CONTENT_SEC", "1")
    monkeypatch.setattr(client, "_post", lambda *a, **k: _Resp())
    monkeypatch.setattr(mc, "_maybe_trip_account_circuit", lambda r: None)
    monkeypatch.setattr(mc, "_verify_quota_response", lambda r, fn: r)

    # 把 time.monotonic 推进，使第二轮迭代即超上界
    ticks = iter([0.0, 0.5, 1.5])
    monkeypatch.setattr(mc.time, "monotonic", lambda: next(ticks, 99.0))

    with pytest.raises(TimeoutError, match="超上界"):
        list(client._stream_one("m", "p", 0.3, None))


def test_call_uses_stream_join_and_fails_closed(monkeypatch):
    """call() 走 call_stream 拼接；失败文本/空内容抛 RuntimeError。"""
    client = mc.ModelScopeClient()

    with patch.object(mc.ModelScopeClient, "call_stream", return_value=iter(["hello ", "world"])):
        assert client.call("p") == "hello world"

    with patch.object(mc.ModelScopeClient, "call_stream",
                      return_value=iter(["[API 调用失败: 全模型不可用]"])):
        with pytest.raises(RuntimeError, match="API 调用失败"):
            client.call("p")

    with patch.object(mc.ModelScopeClient, "call_stream", return_value=iter(["  "])):
        with pytest.raises(RuntimeError, match="空内容"):
            client.call("p")
