# -*- coding: utf-8 -*-
# providers/qwen_client.py
# ---------------------------------------------------------
# Qwen (DashScope) LLMClient 适配器
# ---------------------------------------------------------

import os
import json
import time
import requests
from pathlib import Path
from typing import Generator
from dotenv import load_dotenv

from ..step_executor.interfaces import LLMClient

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

DASHSCOPE_TEXT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

# 重试预算：可选步骤（doc/docstring）曾因上游超时连续重试 1079 秒，
# 把整轮任务拖过 900 秒轮询窗口。网络错误最多重试 1 次，单次读超时 45s，
# 保证最坏情况下单步也有明确上界，不会静默吞掉整轮时间预算。
# G10.20：单次 10s connect timeout + 1 次重试不足以扛住上游网络瞬断；
# 实测 dashscope 抖动会连续打穿整条降级链（shopflow_final_1 的 R8）。
# 2 次退避重试 + 闸门层再包一层，避免基础设施抖动被误判成代码缺陷。
_NETWORK_RETRY_MAX = 2
_NETWORK_RETRY_DELAYS = [2, 6]
_HTTP_TIMEOUT = (10, 45)


# 模型级免费额度耗尽（2026-11-14 实测）：
#   qwen3.7-flash / qwen3.7-max 返回 403 "Free quota exhausted"，
#   而 qwen3.6-plus / qwen3.5-plus / qwen-plus 仍可用。
# 这与 Provider 整体故障不同 —— 不能熔断整个 DashScope，只应把该模型
# 从本次进程的候选链里摘掉，否则每个执行步骤都会重复撞两次 403 白等。
# G10.29：改为带 TTL 的冷却（默认 300s，与 provider_health 的魔搭额度
# 冷却同口径）。长驻 Worker 旧实现是「本进程永久拉黑」：R5 早期一次 403
# 之后，11 分钟后的 R9 即使主链网络已恢复、额度已重新领取，仍把整条候选链
# 全部跳过并吐出失败文本，被 FAIL-CLOSED 正确判成任务失败。冷却到期自动
# 半开重试，无需重启 Worker；真实额度仍耗尽时会重新进入冷却，
# 不改变 FAIL-CLOSED 对失败文本的拦截语义。
_EXHAUSTED_AT: dict = {}
_DEFAULT_QUOTA_COOLDOWN_SEC = 300.0


def _quota_cooldown_sec() -> float:
    raw = (os.getenv("QWEN_QUOTA_COOLDOWN_SEC") or "").strip()
    if not raw:
        return _DEFAULT_QUOTA_COOLDOWN_SEC
    try:
        return max(0.0, float(raw))
    except ValueError:
        return _DEFAULT_QUOTA_COOLDOWN_SEC


def _is_model_cooling(model: str) -> bool:
    """模型是否仍在额度冷却期；到期自动摘除（半开重试）。"""
    marked_at = _EXHAUSTED_AT.get(model)
    if marked_at is None:
        return False
    if time.monotonic() - marked_at >= _quota_cooldown_sec():
        _EXHAUSTED_AT.pop(model, None)
        print(f"[Qwen] 模型 {model} 额度冷却到期，重新纳入候选链")
        return False
    return True


def _is_free_quota_exhausted(response) -> bool:
    try:
        if response.status_code != 403:
            return False
        low = (response.text or "").lower()
        return "free quota exhausted" in low or "quota exhausted" in low
    except Exception:
        return False


def _mark_model_exhausted(model: str) -> None:
    if model and model not in _EXHAUSTED_AT:
        _EXHAUSTED_AT[model] = time.monotonic()
        print(f"[Qwen] 模型 {model} 免费额度耗尽，进入 {_quota_cooldown_sec():.0f}s 冷却")


def reset_exhausted_models() -> None:
    """清除模型级额度冷却（运维恢复额度 / 测试隔离用）。"""
    _EXHAUSTED_AT.clear()


def exhausted_models() -> set:
    """当前仍在冷却期的模型集合（对外暴露时会顺带清理到期项）。"""
    for model in list(_EXHAUSTED_AT):
        _is_model_cooling(model)
    return set(_EXHAUSTED_AT)


def _is_network_error(exc: Exception) -> bool:
    name = type(exc).__name__
    if name in ("SSLEOFError", "SSLError", "ReadTimeout", "ConnectionError",
                 "ConnectionResetError", "RemoteDisconnected", "ProtocolError"):
        return True
    msg = str(exc).lower()
    if "timed out" in msg or "timeout" in msg or "connection" in msg:
        return True
    if "eof occurred in violation of protocol" in msg:
        return True
    return False


def _call_with_retry(fn, max_retries=_NETWORK_RETRY_MAX):
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last_error = e
            if attempt < max_retries and _is_network_error(e):
                delay = _NETWORK_RETRY_DELAYS[min(attempt, len(_NETWORK_RETRY_DELAYS) - 1)]
                print(f"[Qwen] 网络波动 ({type(e).__name__})，{delay}s 后重试 (attempt {attempt + 1}/{max_retries})...")
                time.sleep(delay)
            else:
                raise
    raise last_error


def _extract_text_from_response(data: dict) -> str:
    if "choices" in data and len(data["choices"]) > 0:
        choice = data["choices"][0]
        if "delta" in choice and "content" in choice["delta"]:
            return choice["delta"]["content"]
        if "message" in choice and "content" in choice["message"]:
            return choice["message"]["content"]
    if "output" in data:
        output = data["output"]
        if "text" in output:
            return output["text"]
        if "choices" in output and len(output["choices"]) > 0:
            choice = output["choices"][0]
            if "message" in choice and "content" in choice["message"]:
                return choice["message"]["content"]
    return ""


class QwenClient(LLMClient):
    def __init__(self):
        from ....worker_config import DASHSCOPE_API_KEY
        self._api_key = DASHSCOPE_API_KEY
        # 兜底 Provider 必须真正直连：requests 默认读 HTTP_PROXY/HTTPS_PROXY，
        # 宿主注入的会话代理对 dashscope 域名并不稳定（实测 30s read timeout）。
        # 与 ModelScopeClient 保持同一口径，避免「主链熔断后兜底链也走死路」。
        self._session = requests.Session()
        self._session.trust_env = False

    def _get_chain(self):
        try:
            from ..qwen_model_probe import get_text_fallback_chain
            return get_text_fallback_chain()
        except Exception:
            chain = []
            for key in ["QWEN_MODEL", "QWEN_FALLBACK_1", "QWEN_FALLBACK_2", "QWEN_FALLBACK_3"]:
                val = os.getenv(key)
                if val and val not in chain:
                    chain.append(val)
            if not chain:
                chain = ["qwen-turbo"]
            return chain

    def call(self, prompt: str, temperature: float = 0.3, **kwargs) -> str:
        """阻塞调用内部走 SSE 流式拼接。

        长 Prompt（refine/doc 步骤会带上整个工作区源码）下，非流式接口要等
        整段生成完才返回，实测稳定触发 45s read timeout，单步能烧掉 18 分钟。
        流式接口首 token 即返回，读超时只作用于相邻 chunk 之间，语义等价但
        不会被单次总生成时长卡死。
        """
        if not self._api_key:
            raise RuntimeError("DASHSCOPE_API_KEY 未设置")
        chunks = []
        for chunk in self.call_stream(prompt, temperature):
            if "[API 调用失败" in chunk:
                raise RuntimeError(chunk.strip())
            chunks.append(chunk)
        text = "".join(chunks)
        if not text.strip():
            raise RuntimeError("Qwen 返回空内容")
        return text

    def call_stream(self, prompt: str, temperature: float = 0.3, **kwargs) -> Generator[str, None, None]:
        if not self._api_key:
            yield f"\n\n[API 调用失败: DASHSCOPE_API_KEY 未设置]"
            return

        chain = self._get_chain()
        if not chain:
            yield f"\n\n[API 调用失败: 没有可用的 Qwen 模型]"
            return

        last_error = None
        skipped_exhausted = False
        for model in chain:
            if _is_model_cooling(model):
                skipped_exhausted = True
                print(f"[Qwen Stream] 跳过额度冷却中的模型: {model}")
                continue
            try:
                print(f"[Qwen Stream] 调用模型: {model}")

                def _do_connect():
                    headers = {
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    }
                    body = {
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": temperature,
                        "stream": True,
                    }
                    return self._session.post(
                        DASHSCOPE_TEXT_URL, headers=headers, json=body,
                        timeout=_HTTP_TIMEOUT, stream=True, proxies={},
                    )

                response = _call_with_retry(_do_connect, max_retries=_NETWORK_RETRY_MAX)
                if _is_free_quota_exhausted(response):
                    _mark_model_exhausted(model)
                    last_error = RuntimeError(f"模型 {model} 免费额度耗尽(403)")
                    continue
                response.raise_for_status()
                # SSE 无 charset 时 requests 默认 ISO-8859-1，中文会变 mojibake
                response.encoding = "utf-8"
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            chunk = _extract_text_from_response(data)
                            if chunk:
                                yield chunk
                        except json.JSONDecodeError:
                            continue
                if model != chain[0]:
                    print(f"[Qwen Stream] 降级模型 {model} 调用成功")
                return
            except Exception as e:
                print(f"[Qwen Stream] 模型 {model} 失败: {e}")
                last_error = e
                continue

        if last_error is None and skipped_exhausted:
            yield "\n\n[API 调用失败: 候选链模型免费额度均已耗尽(403)，请领取额度或切换 Provider]"
            return
        yield f"\n\n[API 调用失败: 所有模型不可用 - {last_error}]"