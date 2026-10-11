# -*- coding: utf-8 -*-
# intent_router._classification — LLM 语义分类引擎
# 从 intent_router.py 拆分而来

import json
import os
from typing import Dict

from ._data import ALL_INTENTS, ALL_TARGET_TYPES, LITE_CLASSIFY_PROMPT


def _get_env(key: str, default: str = "") -> str:
    try:
        from worker_config import __dict__ as cfg
        return cfg.get(key, os.environ.get(key, default))
    except Exception:
        return os.environ.get(key, default)


def llm_classify(prompt: str, model_name: str = "qwen") -> Dict:
    try:
        full_prompt = LITE_CLASSIFY_PROMPT + "\n用户：" + prompt
        result_text = call_provider_for_classify(full_prompt, model_name, max_timeout=10)
        if not result_text:
            return None

        json_text = result_text.strip()
        if json_text.startswith("```"):
            json_text = json_text.split("```")[1]
            if json_text.startswith("json"):
                json_text = json_text[4:]
            json_text = json_text.strip()

        parsed = json.loads(json_text)
        intent = parsed.get("intent", "")
        target_type = parsed.get("target_type", "none")
        confidence = float(parsed.get("confidence", 0))

        if intent not in ALL_INTENTS:
            return None
        if target_type not in ALL_TARGET_TYPES:
            target_type = "none"

        return {
            "intent": intent,
            "target_type": target_type,
            "confidence": confidence,
            "reasoning": parsed.get("reasoning", ""),
        }
    except Exception:
        return None


def get_provider_config(model_name: str) -> Dict:
    model_lower = (model_name or "").lower()

    configs = {
        "qwen": {
            "url": "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
            "model": "qwen-turbo",
            "auth_key": "DASHSCOPE_API_KEY",
            "format": "dashscope",
        },
        "gemini": {
            "url": lambda: f"{_get_env('GEMINI_PROXY_URL', 'http://localhost:8000')}/gemini/v1beta/models/{_get_env('GEMINI_MODEL', 'gemini-3.5-flash')}:generateContent",
            "model": lambda: _get_env("GEMINI_MODEL", "gemini-3.5-flash"),
            "auth_key": None,
            "format": "gemini",
        },
        "modelscope": {
            "url": "https://api-inference.modelscope.cn/v1/chat/completions",
            "model": lambda: _get_env("MODELSCOPE_MODEL", "Qwen/Qwen3.8-Flash-Next"),
            "auth_key": "MODELSCOPE_API_KEY",
            "format": "openai",
        },
        "maas": {
            "url": lambda: (_get_env("TENCENT_MAAS_BASE_URL", _get_env("MAAS_URL", "https://tokenhub.tencentmaas.com/v1")).rstrip("/") + "/chat/completions"),
            "model": lambda: _get_env("TENCENT_MAAS_MODEL", "default"),
            "auth_key": "TENCENT_MAAS_API_KEY",
            "alt_auth_key": "TENCENT_MaaS_API_KEY",
            "format": "openai",
        },
        "local": {
            "url": lambda: (_get_env("LOCAL_LLM_BASE_URL", "http://localhost:1234/v1").rstrip("/") + "/chat/completions"),
            "model": lambda: _get_env("LOCAL_LLM_MODEL", "local-model"),
            "auth_key": None,
            "format": "openai",
        },
    }
    return configs.get(model_lower, configs["qwen"])


def call_provider_for_classify(prompt: str, model_name: str, max_timeout: int = 5) -> str:
    import requests
    cfg = get_provider_config(model_name)

    api_format = cfg.get("format", "openai")
    model = cfg["model"]() if callable(cfg["model"]) else cfg["model"]
    url = cfg["url"]() if callable(cfg["url"]) else cfg["url"]

    auth_key = None
    if cfg.get("auth_key"):
        auth_key = _get_env(cfg["auth_key"], "")
    if not auth_key and cfg.get("alt_auth_key"):
        auth_key = _get_env(cfg["alt_auth_key"], "")

    try:
        if api_format == "dashscope":
            if not auth_key:
                return ""
            headers = {"Authorization": f"Bearer {auth_key}", "Content-Type": "application/json"}
            body = {
                "model": model,
                "input": {"prompt": prompt},
                "parameters": {"temperature": 0, "result_format": "message", "max_tokens": 120},
            }
            r = requests.post(url, headers=headers, json=body, timeout=max_timeout)
            r.raise_for_status()
            data = r.json()
            output = data.get("output", {})
            if "choices" in output:
                choices = output.get("choices", [])
                if choices and isinstance(choices, list):
                    return choices[0].get("message", {}).get("content", "")
            return output.get("text", "")

        elif api_format == "gemini":
            headers = {"Content-Type": "application/json"}
            body = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 512},
                "thinkingConfig": {"thinkingBudget": 0},
            }
            r = requests.post(url, headers=headers, json=body, timeout=max_timeout)
            r.raise_for_status()
            data = r.json()
            candidates = data.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {}) or {}
                parts = content.get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            return ""

        elif api_format == "openai":
            if auth_key:
                headers = {"Authorization": f"Bearer {auth_key}", "Content-Type": "application/json"}
            else:
                headers = {"Content-Type": "application/json"}
            body = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are an intent classifier. Return only JSON."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
                "max_tokens": 120,
            }
            r = requests.post(url, headers=headers, json=body, timeout=max_timeout)
            r.raise_for_status()
            data = r.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return ""

    except Exception:
        return ""