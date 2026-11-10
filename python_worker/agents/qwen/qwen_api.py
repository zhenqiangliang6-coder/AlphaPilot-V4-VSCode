# -*- coding: utf-8 -*-
# qwen_api.py
# ---------------------------------------------------------
# Qwen API 调用封装（工业级多模型降级架构）
# - 对齐 DeepSeek deepseek_api.py 的降级模式
# - 模型发现：qwen_model_probe.py 运行时探测 DashScope 可用模型
# - 配置优先：环境变量 QWEN_MODEL / QWEN_FALLBACK_* 覆盖探测结果
# - 所有模型名通过环境变量注入，零硬编码
# ---------------------------------------------------------

import os
import json
import time
import requests
from pathlib import Path
from typing import Generator, Optional, Dict
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from ...worker_config import DASHSCOPE_API_KEY
from .qwen_model_probe import get_text_fallback_chain

DASHSCOPE_TEXT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

_NETWORK_RETRY_MAX = 3
_NETWORK_RETRY_DELAYS = [2, 4, 8]


def _is_network_error(exc: Exception) -> bool:
    """Check if an exception is a transient network error worth retrying."""
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
    """Wrap a callable with retry logic for transient network errors."""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last_error = e
            if attempt < max_retries and _is_network_error(e):
                delay = _NETWORK_RETRY_DELAYS[attempt]
                print(f"[Qwen] 网络波动 ({type(e).__name__})，{delay}s 后重试 (attempt {attempt + 1}/{max_retries})...")
                time.sleep(delay)
            else:
                raise
    raise last_error


def _call_qwen_blocking(prompt: str, model: str, temperature: float = 0.3) -> str:
    def _do():
        headers = {
            "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        r = requests.post(DASHSCOPE_TEXT_URL, headers=headers, json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        return _extract_text_from_response(data)
    return _call_with_retry(_do)


def _call_qwen_sse(prompt: str, model: str, temperature: float = 0.3) -> Generator[str, None, None]:
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "stream": True,
    }

    def _do_connect():
        return requests.post(
            DASHSCOPE_TEXT_URL, headers=headers, json=body, timeout=30, stream=True
        )

    response = _call_with_retry(_do_connect, max_retries=2)
    response.raise_for_status()
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


# ============================================================
# 公共 API（自动降级）
# ============================================================

def call_qwen(prompt: str) -> str:
    """
    调用 Qwen API 进行文本生成（阻塞 + 自动降级）

    降级链来源（按优先级）：
      1. 环境变量 QWEN_MODEL / QWEN_FALLBACK_1 / QWEN_FALLBACK_2 / QWEN_FALLBACK_3
      2. 运行时探测（qwen_model_probe 自动发现 DashScope 可用模型）
      3. 兜底：qwen-turbo
    """
    if not DASHSCOPE_API_KEY:
        raise RuntimeError("DASHSCOPE_API_KEY 未设置")

    chain = get_text_fallback_chain()
    if not chain:
        raise RuntimeError("没有可用的 Qwen 文本模型（探测结果为空且无环境变量配置）")

    last_error = None
    for model in chain:
        try:
            print(f"[Qwen] 调用模型: {model}")
            result = _call_qwen_blocking(prompt, model)
            if model != chain[0]:
                print(f"[Qwen] 降级模型 {model} 调用成功")
            return result
        except Exception as e:
            print(f"[Qwen] 模型 {model} 失败: {e}")
            last_error = e
            continue

    raise RuntimeError(
        f"所有 Qwen 文本模型均不可用 ({', '.join(chain)}): {last_error}"
    )


def call_qwen_stream(prompt: str, temperature: float = 0.3) -> Generator[str, None, None]:
    return call_llm_stream(prompt, temperature)


def call_qwen_with_persona(
    prompt: str,
    persona_config: Optional[Dict] = None,
    use_stream: bool = False,
) -> Generator[str, None, None] | str:
    """
    带人格配置的 Qwen API 调用（自动降级）
    已委托给 call_llm_with_persona 统一入口。
    """
    return call_llm_with_persona(prompt, persona_config, use_stream)


# ============================================================
# ⭐ 统一 LLM 入口（Provider 动态切换）
# ============================================================

def _get_client():
    from .providers import get_cached_llm_client
    return get_cached_llm_client()


def call_llm(prompt: str, temperature: float = 0.3) -> str:
    client = _get_client()
    try:
        return client.call(prompt, temperature=temperature)
    except RuntimeError:
        provider = os.getenv("LLM_PROVIDER", "qwen").lower().strip()
        if provider != "qwen":
            print(f"[Provider] {provider} 全部不可用，自动降级到 DashScope (Qwen)")
            from .providers.qwen_client import QwenClient
            fallback = QwenClient()
            return fallback.call(prompt, temperature=temperature)
        raise


def call_llm_stream(prompt: str, temperature: float = 0.3) -> Generator[str, None, None]:
    client = _get_client()
    provider = os.getenv("LLM_PROVIDER", "qwen").lower().strip()

    gen = client.call_stream(prompt, temperature=temperature)
    if provider != "qwen":
        first = next(gen, None)
        if first and "[API 调用失败" in str(first):
            print(f"[Provider] {provider} 流式全部不可用，自动降级到 DashScope (Qwen)")
            from .providers.qwen_client import QwenClient
            fallback = QwenClient()
            yield from fallback.call_stream(prompt, temperature=temperature)
            return
        if first:
            yield first
        yield from gen
        return

    yield from gen


def call_llm_with_persona(
    prompt: str,
    persona_config: Optional[Dict] = None,
    use_stream: bool = False,
) -> Generator[str, None, None] | str:
    if persona_config:
        system_prompt = persona_config.get("system_prompt", "")
        full_prompt = f"{system_prompt}\n\n---\n\n用户请求:\n{prompt}"
    else:
        full_prompt = prompt

    if use_stream:
        return call_llm_stream(full_prompt)
    else:
        return call_llm(full_prompt)