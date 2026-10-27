# -*- coding: utf-8 -*-
# modelscope_api.py
# ---------------------------------------------------------
# ModelScope API 调用封装（ModelScope 平台）
# - 模型降级链：环境变量配置，按顺序自动降级
# ---------------------------------------------------------

import json
import os
import time
from pathlib import Path
from typing import List

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

MODELSCOPE_API_KEY = os.getenv("MODELSCOPE_API_KEY")
MODELSCOPE_MODEL = os.getenv("MODELSCOPE_MODEL", "Qwen/Qwen3.8-Flash-Next")
MODELSCOPE_BASE_URL = os.getenv(
    "MODELSCOPE_BASE_URL",
    os.getenv("MODELSCOPE_URL", "https://api-inference.modelscope.cn/v1"),
).rstrip("/")
MODELSCOPE_URL = MODELSCOPE_BASE_URL
if not MODELSCOPE_URL.endswith("/chat/completions"):
    MODELSCOPE_URL += "/chat/completions"

MODELSCOPE_CONNECT_TIMEOUT_SECONDS = float(
    os.getenv("MODELSCOPE_CONNECT_TIMEOUT_SECONDS", "10")
)
MODELSCOPE_READ_TIMEOUT_SECONDS = float(
    os.getenv("MODELSCOPE_READ_TIMEOUT_SECONDS", "600")
)
MODELSCOPE_MAX_RETRIES = max(0, int(os.getenv("MODELSCOPE_MAX_RETRIES", "3")))
MODELSCOPE_RETRY_BACKOFF_SECONDS = float(
    os.getenv("MODELSCOPE_RETRY_BACKOFF_SECONDS", "2")
)
RETRYABLE_STATUS_CODES = (500, 502, 503, 504)
REQUEST_TIMEOUT = (
    MODELSCOPE_CONNECT_TIMEOUT_SECONDS,
    MODELSCOPE_READ_TIMEOUT_SECONDS,
)


def _get_fallback_chain() -> List[str]:
    """从环境变量构建模型降级链"""
    chain = []
    for key in [
        "MODELSCOPE_MODEL",
        "MODELSCOPE_FALLBACK_1",
        "MODELSCOPE_FALLBACK_2",
        "MODELSCOPE_FALLBACK_3",
        "MODELSCOPE_FALLBACK_4",
        "MODELSCOPE_FALLBACK_5",
    ]:
        val = os.getenv(key)
        if val and val not in chain:
            chain.append(val)
    if not chain:
        chain = ["Qwen/Qwen3.8-Flash-Next"]
    return chain


def _make_session(read_retries: int) -> requests.Session:
    retry = Retry(
        total=MODELSCOPE_MAX_RETRIES,
        connect=MODELSCOPE_MAX_RETRIES,
        read=read_retries,
        status=MODELSCOPE_MAX_RETRIES,
        backoff_factor=MODELSCOPE_RETRY_BACKOFF_SECONDS,
        status_forcelist=RETRYABLE_STATUS_CODES,
        allowed_methods=frozenset({"POST"}),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


# Requests consumes non-streamed bodies after the adapter returns, so body
# timeouts are retried around the complete request below.
SESSION = _make_session(read_retries=0)
# Streaming body reads are also retried around request + iteration below.
STREAM_SESSION = requests.Session()


def _headers() -> dict:
    if not MODELSCOPE_API_KEY:
        raise ValueError("MODELSCOPE_API_KEY 未设置（请检查 .env 文件）")
    return {
        "Authorization": f"Bearer {MODELSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }


def _payload(prompt: str, stream: bool, system_prompt: str = None, model: str = None) -> dict:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    return {
        "model": model or MODELSCOPE_MODEL,
        "stream": stream,
        "messages": messages,
    }


def _stream_chunks(response):
    response.raise_for_status()
    for line in response.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8") if isinstance(line, bytes) else line
        if not decoded.startswith("data: "):
            continue

        data_str = decoded[6:]
        if data_str.strip() == "[DONE]":
            return
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            continue
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("delta", {}).get("content", "")
            if content:
                yield content


def _request_stream(prompt: str, system_prompt: str = None, model: str = None):
    headers = _headers()
    payload = _payload(prompt, stream=True, system_prompt=system_prompt, model=model)
    last_error = None

    for attempt in range(MODELSCOPE_MAX_RETRIES + 1):
        emitted_content = False
        try:
            with STREAM_SESSION.post(
                MODELSCOPE_URL,
                headers=headers,
                json=payload,
                stream=True,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                for chunk in _stream_chunks(response):
                    emitted_content = True
                    yield chunk
            return
        except requests.RequestException as error:
            last_error = error
            status_code = getattr(getattr(error, "response", None), "status_code", None)
            retryable = isinstance(
                error,
                (
                    requests.exceptions.Timeout,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.ChunkedEncodingError,
                ),
            ) or status_code in RETRYABLE_STATUS_CODES
            if (
                emitted_content
                or not retryable
                or attempt >= MODELSCOPE_MAX_RETRIES
            ):
                raise
            delay = MODELSCOPE_RETRY_BACKOFF_SECONDS * (2**attempt)
            if delay:
                time.sleep(delay)

    if last_error:
        raise last_error


def call_modelscope(prompt: str, stream: bool = False, system_prompt: str = None) -> str:
    """
    调用 ModelScope API 进行文本生成。

    模型降级链：按环境变量 MODELSCOPE_MODEL → MODELSCOPE_FALLBACK_1 → ... 顺序尝试。
    连接超时、响应读取超时和指定的服务端错误会有限次自动重试。
    
    参数:
        prompt: 用户提示词
        stream: 是否流式返回
        system_prompt: 系统提示词（人格配置等），可选
    """
    if stream:
        return _call_with_fallback_stream(prompt, system_prompt)

    return _call_with_fallback(prompt, system_prompt)


def _call_with_fallback(prompt: str, system_prompt: str = None) -> str:
    """非流式调用 + 模型降级"""
    chain = _get_fallback_chain()
    last_error = None

    for model in chain:
        headers = _headers()
        payload = _payload(prompt, stream=False, system_prompt=system_prompt, model=model)
        try:
            print(f"[ModelScope] 调用模型: {model}")
            response = SESSION.post(
                MODELSCOPE_URL,
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                raise ValueError(f"ModelScope API 返回空响应：{data}")

            content = choices[0].get("message", {}).get("content", "")
            if not content:
                raise ValueError(f"ModelScope API 返回空内容：{data}")
            if model != chain[0]:
                print(f"[ModelScope] 降级模型 {model} 调用成功")
            return content

        except requests.exceptions.ReadTimeout as e:
            last_error = e
            print(f"[ModelScope] 模型 {model} 读超时，尝试下一个...")
            continue
        except requests.RequestException as e:
            last_error = e
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status is not None and status not in RETRYABLE_STATUS_CODES:
                print(f"[ModelScope] 模型 {model} 返回 {status}，尝试下一个...")
                continue
            if model == chain[-1]:
                raise
            print(f"[ModelScope] 模型 {model} 失败: {e}，尝试下一个...")
            continue
        except ValueError as e:
            last_error = e
            print(f"[ModelScope] 模型 {model} 返回无效: {e}，尝试下一个...")
            if model == chain[-1]:
                raise
            continue

    raise RuntimeError(f"所有 ModelScope 模型均不可用 ({', '.join(chain)}): {last_error}")


def _call_with_fallback_stream(prompt: str, system_prompt: str = None) -> str:
    """流式调用 + 模型降级"""
    chain = _get_fallback_chain()
    last_error = None

    for model in chain:
        try:
            print(f"[ModelScope] 流式调用: {model}")
            result = "".join(_request_stream(prompt, system_prompt=system_prompt, model=model))
            if result:
                if model != chain[0]:
                    print(f"[ModelScope] 降级模型 {model} 流式调用成功")
                return result
            last_error = ValueError(f"模型 {model} 返回空流内容")
        except requests.RequestException as e:
            last_error = e
            print(f"[ModelScope] 模型 {model} 流式失败: {e}，尝试下一个...")
            continue
        except ValueError as e:
            last_error = e
            print(f"[ModelScope] 模型 {model} 流式返回无效: {e}，尝试下一个...")
            continue

    raise RuntimeError(f"所有 ModelScope 模型流式均不可用 ({', '.join(chain)}): {last_error}")


def call_modelscope_stream(prompt: str, system_prompt: str = None):
    """以生成器方式流式调用 ModelScope API（带模型降级链）。"""
    chain = _get_fallback_chain()
    last_error = None

    for model in chain:
        try:
            print(f"[ModelScope] 流式生成: {model}")
            emitted = False
            for chunk in _request_stream(prompt, system_prompt=system_prompt, model=model):
                emitted = True
                yield chunk
            if emitted:
                if model != chain[0]:
                    print(f"[ModelScope] 降级模型 {model} 流式生成成功")
                return
            last_error = ValueError(f"模型 {model} 返回空流内容")
        except requests.RequestException as e:
            last_error = e
            print(f"[ModelScope] 模型 {model} 流式失败: {e}，尝试下一个...")
            continue
        except ValueError as e:
            last_error = e
            print(f"[ModelScope] 模型 {model} 流式返回无效: {e}，尝试下一个...")
            continue

    raise RuntimeError(f"所有 ModelScope 模型流式均不可用 ({', '.join(chain)}): {last_error}")