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

_NETWORK_RETRY_MAX = 3
_NETWORK_RETRY_DELAYS = [2, 4, 8]


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
                delay = _NETWORK_RETRY_DELAYS[attempt]
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
        if not self._api_key:
            raise RuntimeError("DASHSCOPE_API_KEY 未设置")

        chain = self._get_chain()
        if not chain:
            raise RuntimeError("没有可用的 Qwen 文本模型")

        last_error = None
        for model in chain:
            try:
                print(f"[Qwen] 调用模型: {model}")

                def _do():
                    headers = {
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    }
                    body = {
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": temperature,
                    }
                    r = requests.post(DASHSCOPE_TEXT_URL, headers=headers, json=body, timeout=30)
                    r.raise_for_status()
                    return _extract_text_from_response(r.json())

                result = _call_with_retry(_do)
                if model != chain[0]:
                    print(f"[Qwen] 降级模型 {model} 调用成功")
                return result
            except Exception as e:
                print(f"[Qwen] 模型 {model} 失败: {e}")
                last_error = e
                continue

        raise RuntimeError(f"所有 Qwen 文本模型均不可用 ({', '.join(chain)}): {last_error}")

    def call_stream(self, prompt: str, temperature: float = 0.3, **kwargs) -> Generator[str, None, None]:
        if not self._api_key:
            yield f"\n\n[API 调用失败: DASHSCOPE_API_KEY 未设置]"
            return

        chain = self._get_chain()
        if not chain:
            yield f"\n\n[API 调用失败: 没有可用的 Qwen 模型]"
            return

        last_error = None
        for model in chain:
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
                    return requests.post(DASHSCOPE_TEXT_URL, headers=headers, json=body, timeout=30, stream=True)

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
                if model != chain[0]:
                    print(f"[Qwen Stream] 降级模型 {model} 调用成功")
                return
            except Exception as e:
                print(f"[Qwen Stream] 模型 {model} 失败: {e}")
                last_error = e
                continue

        yield f"\n\n[API 调用失败: 所有模型不可用 - {last_error}]"