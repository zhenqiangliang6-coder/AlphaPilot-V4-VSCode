# -*- coding: utf-8 -*-
# providers/doubao_client.py
# ---------------------------------------------------------
# 火山引擎豆包 (Doubao) LLMClient 适配器
# ---------------------------------------------------------

import json
import os
import time
from typing import Generator

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from pathlib import Path
from ..step_executor.interfaces import LLMClient

load_dotenv(Path(__file__).resolve().parents[3] / ".env")


def _create_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.trust_env = False
    session.proxies = {'http': None, 'https': None}
    return session


def _extract_text(result: dict) -> str:
    if "output" in result and isinstance(result["output"], list):
        output_list = result["output"]
        if output_list and len(output_list) > 0:
            first_output = output_list[0]
            if "summary" in first_output:
                for item in first_output["summary"]:
                    if item.get("type") == "summary_text":
                        text = item.get("text", "")
                        if text:
                            return text
            if "content" in first_output:
                content_list = first_output["content"]
                if content_list and len(content_list) > 0:
                    text = content_list[0].get("text", "")
                    if text:
                        return text
    if "choices" in result:
        choices = result["choices"]
        if choices and len(choices) > 0:
            return choices[0].get("message", {}).get("content", "")
    return ""


class DoubaoClient(LLMClient):
    def __init__(self):
        self._api_key = os.getenv("VOLC_API_KEY")
        self._model = os.getenv("DOUBAO_MODEL", "doubao-seed-2-0-lite-260215")
        self._base_url = "https://ark.cn-beijing.volces.com/api/v3/responses"

    def call(self, prompt: str, temperature: float = 0.3, **kwargs) -> str:
        if not self._api_key:
            raise ValueError("VOLC_API_KEY 未设置")

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self._model,
            "input": [{
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}]
            }]
        }

        session = _create_session()
        try:
            response = session.post(self._base_url, headers=headers, json=payload, timeout=300)
            response.raise_for_status()
            result = response.json()
            text = _extract_text(result)
            if not text:
                print(f"[Doubao] API 返回格式无法解析: {json.dumps(result, ensure_ascii=False)[:500]}")
            return text
        finally:
            session.close()

    def call_stream(self, prompt: str, temperature: float = 0.3, **kwargs) -> Generator[str, None, None]:
        if not self._api_key:
            yield f"\n\n[API 调用失败: VOLC_API_KEY 未设置]"
            return

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self._model,
            "input": [{
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}]
            }],
            "stream": True
        }

        session = _create_session()
        try:
            response = session.post(
                self._base_url + "/stream" if not self._base_url.endswith("/stream") else self._base_url,
                headers=headers, json=payload, timeout=300, stream=True
            )
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
                        text = _extract_text(data)
                        if text:
                            yield text
                    except json.JSONDecodeError:
                        continue
        finally:
            session.close()