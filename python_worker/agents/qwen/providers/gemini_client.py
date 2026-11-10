# -*- coding: utf-8 -*-
# providers/gemini_client.py
# ---------------------------------------------------------
# Google Gemini LLMClient 适配器
# - 通过 AlphaPilot International Proxy 转发
# ---------------------------------------------------------

import json
import os
from pathlib import Path
from typing import Generator

import requests
from dotenv import load_dotenv

from ..step_executor.interfaces import LLMClient

load_dotenv(Path(__file__).resolve().parents[3] / ".env")


class GeminiClient(LLMClient):
    def __init__(self):
        self._proxy_url = os.getenv("GEMINI_PROXY_URL", "")
        self._model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
        self._timeout = int(os.getenv("GEMINI_TIMEOUT", "300"))
        self._max_tokens = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "8192"))
        self._temperature = float(os.getenv("GEMINI_TEMPERATURE", "0.3"))

    def _url(self, stream: bool = False) -> str:
        suffix = "streamGenerateContent" if stream else "generateContent"
        return f"{self._proxy_url}/gemini/v1beta/models/{self._model}:{suffix}"

    def _body(self, prompt: str) -> dict:
        return {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self._temperature,
                "maxOutputTokens": self._max_tokens,
            }
        }

    def call(self, prompt: str, temperature: float = 0.3, **kwargs) -> str:
        if not self._proxy_url:
            raise ValueError("GEMINI_PROXY_URL 未设置")

        try:
            r = requests.post(
                self._url(stream=False),
                headers={"Content-Type": "application/json"},
                json=self._body(prompt),
                timeout=self._timeout
            )
            r.raise_for_status()
            data = r.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            raise ValueError(f"Gemini API 响应格式异常: {e}")

    def call_stream(self, prompt: str, temperature: float = 0.3, **kwargs) -> Generator[str, None, None]:
        if not self._proxy_url:
            yield f"\n\n[API 调用失败: GEMINI_PROXY_URL 未设置]"
            return

        try:
            response = requests.post(
                self._url(stream=True),
                headers={"Content-Type": "application/json"},
                json=self._body(prompt),
                timeout=self._timeout,
                stream=True
            )
            response.raise_for_status()

            buffer = ""
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith('data:'):
                    data_str = line[5:].strip()
                    if data_str == '[DONE]':
                        break
                    try:
                        data = json.loads(data_str)
                        text = self._extract_text(data)
                        if text:
                            yield text
                    except json.JSONDecodeError:
                        continue
                else:
                    buffer += line
                    try:
                        data = json.loads(buffer)
                        text = self._extract_text(data)
                        if text:
                            yield text
                        buffer = ""
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"[Gemini] 流式 API 调用失败: {e}")
            yield f"\n\n[API 调用失败: {str(e)}]"

    def _extract_text(self, data: dict) -> str:
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            return ""