# -*- coding: utf-8 -*-
# modelscope_api.py
# ---------------------------------------------------------
# ModelScope API 调用封装（ModelScope 平台）
# ---------------------------------------------------------

import json
import os
import time
from pathlib import Path

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


def _payload(prompt: str, stream: bool) -> dict:
    return {
        "model": MODELSCOPE_MODEL,
        "stream": stream,
        "messages": [{"role": "user", "content": prompt}],
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


def _request_stream(prompt: str):
    headers = _headers()
    payload = _payload(prompt, stream=True)
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


def call_modelscope(prompt: str, stream: bool = False) -> str:
    """
    调用 ModelScope API 进行文本生成。

    连接超时、响应读取超时和指定的服务端错误会有限次自动重试。
    """
    if stream:
        return "".join(_request_stream(prompt))

    headers = _headers()
    payload = _payload(prompt, stream=False)
    for attempt in range(MODELSCOPE_MAX_RETRIES + 1):
        try:
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
            return content
        except requests.exceptions.ReadTimeout:
            if attempt >= MODELSCOPE_MAX_RETRIES:
                raise
            delay = MODELSCOPE_RETRY_BACKOFF_SECONDS * (2**attempt)
            if delay:
                time.sleep(delay)


def call_modelscope_stream(prompt: str):
    """以生成器方式流式调用 ModelScope API。"""
    yield from _request_stream(prompt)
