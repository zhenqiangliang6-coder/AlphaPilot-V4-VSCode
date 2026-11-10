# -*- coding: utf-8 -*-
# providers/openai_compatible_client.py
# ---------------------------------------------------------
# OpenAI 兼容格式 LLMClient 适配器
# - 支持 OpenAI / Local LLM (LM Studio) / 任何 v1/chat/completions 端点
# - 自动检测 system + user message 拆分
# ---------------------------------------------------------

import json
import os
import time
from pathlib import Path
from typing import Generator

import requests
from dotenv import load_dotenv

from ..step_executor.interfaces import LLMClient

load_dotenv(Path(__file__).resolve().parents[3] / ".env")


class OpenAICompatibleClient(LLMClient):
    def __init__(self):
        provider = os.getenv("LLM_PROVIDER", "openai").lower()

        if provider == "local":
            self._api_key = os.getenv("LOCAL_LLM_API_KEY", "not-needed")
            self._model = os.getenv("LOCAL_LLM_MODEL", "google/gemma-4-e4b")
            self._url = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:1234/v1").rstrip("/") + "/chat/completions"
            self._timeout = int(os.getenv("LOCAL_LLM_TIMEOUT", "300"))
            self._retries = int(os.getenv("LOCAL_LLM_RETRIES", "2"))
        else:
            self._api_key = os.getenv("OPENAI_API_KEY")
            self._model = os.getenv("OPENAI_MODEL", "gpt-4o")
            self._url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
            self._timeout = int(os.getenv("OPENAI_TIMEOUT", "300"))
            self._retries = int(os.getenv("OPENAI_RETRIES", "2"))

    def _build_messages(self, prompt: str, system_prompt: str = None) -> list:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            return messages

        if "---" in prompt and prompt.count("---") >= 1:
            parts = prompt.split("---", 1)
            if len(parts) == 2:
                system_content = parts[0].strip()
                user_content = parts[1].strip()
                if any(kw in system_content for kw in ["核心规则", "必须遵守", "禁止输出", "正确示例"]):
                    return [
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": user_content}
                    ]
        return [{"role": "user", "content": prompt}]

    def call(self, prompt: str, temperature: float = 0.3, **kwargs) -> str:
        if not self._api_key and os.getenv("LLM_PROVIDER", "") != "local":
            raise ValueError("OPENAI_API_KEY 未设置")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}"
        }

        body = {
            "model": self._model,
            "messages": self._build_messages(prompt, kwargs.get("system_prompt")),
            "temperature": temperature,
            "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", "4096")),
        }

        last_error = None
        for attempt in range(self._retries + 1):
            try:
                r = requests.post(self._url, headers=headers, json=body, timeout=self._timeout)
                r.raise_for_status()
                data = r.json()
                choices = data.get("choices", [])
                if choices:
                    msg = choices[0].get("message", {})
                    content = msg.get("content", "") or msg.get("reasoning_content", "")
                    return content
                raise ValueError(f"未知响应格式: {list(data.keys())}")
            except requests.exceptions.Timeout as e:
                last_error = e
                if attempt < self._retries:
                    time.sleep(1)
                    continue
                raise TimeoutError(f"API 调用超时（{self._timeout} 秒），重试 {self._retries} 次后失败")
            except requests.exceptions.ConnectionError as e:
                raise ConnectionError(f"无法连接到 API 服务 ({self._url})")
            except Exception as e:
                last_error = e
                if attempt < self._retries:
                    time.sleep(1)
                    continue
                raise RuntimeError(f"API 调用失败: {str(e)}")

        if last_error:
            raise last_error

    def call_stream(self, prompt: str, temperature: float = 0.3, **kwargs) -> Generator[str, None, None]:
        if not self._api_key and os.getenv("LLM_PROVIDER", "") != "local":
            yield f"\n\n[API 调用失败: API Key 未设置]"
            return

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}"
        }

        body = {
            "model": self._model,
            "messages": self._build_messages(prompt, kwargs.get("system_prompt")),
            "temperature": temperature,
            "stream": True,
            "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", "4096")),
        }

        try:
            with requests.post(self._url, headers=headers, json=body, timeout=self._timeout, stream=True) as r:
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
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "") or delta.get("reasoning_content", "")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            print(f"[OpenAI-Compatible] 流式 API 调用失败: {e}")
            yield f"\n\n[API 调用失败: {str(e)}]"