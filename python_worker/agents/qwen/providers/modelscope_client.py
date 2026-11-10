# -*- coding: utf-8 -*-
# providers/modelscope_client.py
# ---------------------------------------------------------
# ModelScope LLMClient 适配器（v2.1 — 动态 max_tokens + 多文件预算估算）
# - 模型降级链：环境变量配置，按顺序自动降级
# - 网络重试：3 次 + [2,4,8]s 指数退避
# - 动态 max_tokens：根据 prompt 中 # FILE: 块数估算输出预算，避免截断
# - Qwen thinking 自动关闭：长 prompt 响应从 >120s 降至 ~30s
# ---------------------------------------------------------

import json
import os
import time
from pathlib import Path
from typing import Generator, List

import requests
from dotenv import load_dotenv

from ..step_executor.interfaces import LLMClient

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

# ============================================================
# 网络重试策略（对齐 qwen_client.py 的 _is_network_error + _call_with_retry）
# ============================================================
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
                print(f"[ModelScope] 网络波动 ({type(e).__name__})，{delay}s 后重试 "
                      f"(attempt {attempt + 1}/{max_retries})...")
                time.sleep(delay)
            else:
                raise
    raise last_error


def _extract_text_from_response(data: dict) -> str:
    if "choices" in data and len(data["choices"]) > 0:
        choice = data["choices"][0]
        # 优先 message.content（非流式），Qwen 开启 chat_template_kwargs 后两者共存
        if "message" in choice and choice["message"].get("content"):
            return choice["message"]["content"]
        if "delta" in choice and "content" in choice["delta"]:
            return choice["delta"]["content"]
        # 回退：message 存在但 content 为空（可能是流式首次包）
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
class ModelScopeClient(LLMClient):
    def __init__(self):
        self._api_key = os.getenv("MODELSCOPE_API_KEY")
        self._base_url = os.getenv("MODELSCOPE_BASE_URL",
                                    os.getenv("MODELSCOPE_URL",
                                              "https://api-inference.modelscope.cn/v1")).rstrip("/")
        if not self._base_url.endswith("/chat/completions"):
            self._base_url += "/chat/completions"

        self._model = os.getenv("MODELSCOPE_MODEL", "Qwen/Qwen3.8-Flash-Next")

        self._connect_timeout = float(os.getenv("MODELSCOPE_CONNECT_TIMEOUT_SECONDS", "10"))
        self._read_timeout = float(os.getenv("MODELSCOPE_READ_TIMEOUT_SECONDS", "60"))

        self._max_tokens = int(os.getenv("MODELSCOPE_MAX_TOKENS", "4096"))

        self._max_retries = max(0, int(os.getenv("MODELSCOPE_MAX_RETRIES", "3")))
        self._backoff = float(os.getenv("MODELSCOPE_RETRY_BACKOFF_SECONDS", "2"))

    def _get_chain(self) -> List[str]:
        chain = []
        for key in ["MODELSCOPE_MODEL", "MODELSCOPE_FALLBACK_1", "MODELSCOPE_FALLBACK_2",
                     "MODELSCOPE_FALLBACK_3", "MODELSCOPE_FALLBACK_4", "MODELSCOPE_FALLBACK_5"]:
            val = os.getenv(key)
            if val and val not in chain:
                chain.append(val)
        if not chain:
            chain = ["Qwen/Qwen3.8-Flash-Next"]
        return chain

    def _headers(self) -> dict:
        if not self._api_key:
            raise ValueError("MODELSCOPE_API_KEY 未设置")
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, prompt: str, stream: bool, model: str = None,
                 temperature: float = 0.3, max_tokens: int = None,
                 system_prompt: str = None) -> dict:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        current_model = model or self._model
        body = {
            "model": current_model,
            "stream": stream,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens if max_tokens is not None else self._max_tokens,
        }
        # Qwen3.5+ 默认开启思考模式，导致长 prompt 极慢；必须显式关闭
        if "qwen" in current_model.lower():
            body["chat_template_kwargs"] = {"enable_thinking": False}
        return body

    def _timeout(self):
        return (self._connect_timeout, self._read_timeout)

    # ── v2.1 动态 max_tokens 估算 ────────────────────────────
    # 基于 prompt 内容（# FILE: 块数量）动态计算所需的输出 token 预算，
    # 避免多文件生成时硬编码值导致输出截断。
    # 公式：max(max_tokens_from_env, #FILE块数 × 2500 + 1000)
    # 上限：16384 tokens（Qwen3.8 安全上限，thinking 关闭后足够）
    _MAX_TOKENS_CEILING = 16384

    def _estimate_output_tokens(self, prompt: str) -> int:
        file_blocks = prompt.count("# FILE:")
        test_blocks = prompt.count("# TEST:")
        total_blocks = file_blocks + test_blocks

        if total_blocks == 0:
            return self._max_tokens

        per_file_budget = 2500
        estimated = total_blocks * per_file_budget + 1000
        return min(max(self._max_tokens, estimated), self._MAX_TOKENS_CEILING)

    def call(self, prompt: str, temperature: float = 0.3, **kwargs) -> str:
        chain = self._get_chain()
        if not self._api_key:
            raise RuntimeError("MODELSCOPE_API_KEY 未设置")

        headers = self._headers()
        last_error = None

        for model in chain:
            try:
                print(f"[ModelScope] 调用模型: {model}")

                estimated_tokens = self._estimate_output_tokens(prompt)

                def _do():
                    body = self._payload(
                        prompt, stream=False, model=model,
                        temperature=temperature,
                        max_tokens=estimated_tokens,
                        system_prompt=kwargs.get("system_prompt"),
                    )
                    r = requests.post(
                        self._base_url, headers=headers, json=body,
                        timeout=self._timeout(),
                    )
                    r.raise_for_status()
                    return _extract_text_from_response(r.json())

                result = _call_with_retry(_do)
                if not result:
                    raise ValueError(f"ModelScope 模型 {model} 返回空内容")
                if model != chain[0]:
                    print(f"[ModelScope] 降级模型 {model} 调用成功")
                return result
            except Exception as e:
                print(f"[ModelScope] 模型 {model} 失败: {e}")
                last_error = e
                continue

        raise RuntimeError(
            f"所有 ModelScope 模型均不可用 ({', '.join(chain)}): {last_error}"
        )

    def call_stream(self, prompt: str, temperature: float = 0.3, **kwargs) -> Generator[str, None, None]:
        chain = self._get_chain()
        if not self._api_key:
            yield f"\n\n[API 调用失败: MODELSCOPE_API_KEY 未设置]"
            return

        headers = self._headers()
        system_prompt = kwargs.get("system_prompt")
        last_error = None

        for model in chain:
            try:
                print(f"[ModelScope] 流式调用: {model}")

                def _do_connect():
                    body = self._payload(
                        prompt, stream=True, model=model,
                        temperature=temperature, system_prompt=system_prompt,
                    )
                    return requests.post(
                        self._base_url, headers=headers, json=body,
                        timeout=self._timeout(), stream=True,
                    )

                response = _call_with_retry(_do_connect, max_retries=2)
                response.raise_for_status()
                emitted = False
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        chunk = _extract_text_from_response(data)
                        if chunk:
                            emitted = True
                            yield chunk
                if emitted:
                    if model != chain[0]:
                        print(f"[ModelScope] 降级模型 {model} 流式调用成功")
                    return
                last_error = ValueError(f"模型 {model} 返回空流内容")
            except Exception as e:
                print(f"[ModelScope] 模型 {model} 流式失败: {e}")
                last_error = e
                continue

        yield f"\n\n[API 调用失败: 所有模型不可用 - {last_error}]"