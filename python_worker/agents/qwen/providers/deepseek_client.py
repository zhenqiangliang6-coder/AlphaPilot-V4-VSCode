# -*- coding: utf-8 -*-
# providers/deepseek_client.py
# ---------------------------------------------------------
# DeepSeek LLMClient 适配器
# - 通过火山引擎 DeepSeek 端点接入
# - 标准 Chat Completions API 格式
# ---------------------------------------------------------

import json
import os
from pathlib import Path
from typing import Generator

import requests
from dotenv import load_dotenv

from ..step_executor.interfaces import LLMClient

load_dotenv(Path(__file__).resolve().parents[3] / ".env")


class DeepSeekClient(LLMClient):
    def __init__(self):
        self._api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("VOLC_API_KEY")
        self._model = os.getenv("DEEPSEEK_MODEL", "deepseek-v3-250324")
        self._url = os.getenv("DEEPSEEK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3/chat/completions")

    def _headers(self) -> dict:
        if not self._api_key:
            raise ValueError("DEEPSEEK_API_KEY 或 VOLC_API_KEY 未设置")
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def call(self, prompt: str, temperature: float = 0.3, **kwargs) -> str:
        body = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        r = requests.post(self._url, headers=self._headers(), json=body, timeout=300)
        r.raise_for_status()
        data = r.json()
        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
        raise ValueError(f"DeepSeek API 返回格式异常: {json.dumps(data, ensure_ascii=False)[:500]}")

    def call_stream(self, prompt: str, temperature: float = 0.3, **kwargs) -> Generator[str, None, None]:
        body = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "stream": True,
        }
        try:
            with requests.post(self._url, headers=self._headers(), json=body, timeout=300, stream=True) as r:
                r.raise_for_status()
                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            choices = data.get("choices", [])
                            if choices:
                                content = choices[0].get("delta", {}).get("content", "")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            print(f"[DeepSeek] 流式 API 调用失败: {e}")
            yield f"\n\n[API 调用失败: {str(e)}]"