# -*- coding: utf-8 -*-
# intent_router._classification — LLM 语义分类引擎
# 从 intent_router.py 拆分而来

import json
import os
import time
from typing import Dict, List

from ._data import ALL_INTENTS, ALL_TARGET_TYPES, LITE_CLASSIFY_PROMPT


def _get_env(key: str, default: str = "") -> str:
    try:
        from worker_config import __dict__ as cfg
        return cfg.get(key, os.environ.get(key, default))
    except Exception:
        return os.environ.get(key, default)


_CHAIN_CACHE = None
_CHAIN_CACHE_TS = 0
_CHAIN_CACHE_TTL = 3600


def _resolve_qwen_classify_chain() -> List[str]:
    """从 Qwen 模型探测中动态获取可用的文本模型降级链。

    绝不硬编码任何模型名。每次调用均从探针缓存读取最新的
    /v1/models + 可用性验证结果，构造真实验证的降级链。

    优先级：
      1. INTENT_CLASSIFY_MODEL 环境变量（显式指定）
      2. 模型探测 text 链（API 返回 + 可用性验证的全部文本模型）
      3. 模型探测 best_text（至少一个经过验证的模型）
      4. QWEN_MODEL 环境变量
      5. 绝对兜底（单模型）
    """
    global _CHAIN_CACHE, _CHAIN_CACHE_TS

    env_model = os.environ.get("INTENT_CLASSIFY_MODEL", "").strip()
    if env_model:
        return [env_model]

    now = time.time()
    if _CHAIN_CACHE is not None and (now - _CHAIN_CACHE_TS) < _CHAIN_CACHE_TTL:
        return _CHAIN_CACHE

    try:
        try:
            from ..agents.qwen.qwen_model_probe import probe_qwen_models
        except ImportError:
            from agents.qwen.qwen_model_probe import probe_qwen_models

        probed = probe_qwen_models()
        text_chain = probed.get("text", [])
        if text_chain:
            _CHAIN_CACHE = text_chain
            _CHAIN_CACHE_TS = now
            return text_chain

        best = probed.get("best_text", "")
        if best:
            _CHAIN_CACHE = [best]
            _CHAIN_CACHE_TS = now
            return [best]
    except Exception as e:
        print(f"\n⚠️ [Intent Router] 模型探测失败: {type(e).__name__}: {e}")

    qwen_model = os.environ.get("QWEN_MODEL", "").strip()
    if qwen_model:
        _CHAIN_CACHE = [qwen_model]
        _CHAIN_CACHE_TS = now
        return [qwen_model]

    print("⚠️ [Intent Router] 无法探测模型池，使用绝对兜底")
    fallback = ["qwen3.8-max"]
    _CHAIN_CACHE = fallback
    _CHAIN_CACHE_TS = now
    return fallback


def llm_classify(prompt: str, model_name: str = "qwen") -> Dict:
    full_prompt = LITE_CLASSIFY_PROMPT + "\n用户：" + prompt

    if model_name == "qwen":
        chain = _resolve_qwen_classify_chain()
    else:
        chain = [None]

    last_error = None
    for idx, model in enumerate(chain):
        try:
            result_text = call_provider_for_classify(
                full_prompt, model_name, model_override=model, max_timeout=10
            )
        except Exception as e:
            last_error = e
            if len(chain) > 1:
                print(f"   ⚠️ [Intent Router] 模型 '{model}' 调用异常，尝试下一个...")
            continue

        if not result_text:
            if len(chain) > 1:
                print(f"   ⚠️ [Intent Router] 模型 '{model}' 不可用，尝试下一个...")
            continue

        if idx == 0:
            print(f"   ✅ [Intent Router] 模型 '{model}' 分类成功")

        json_text = result_text.strip()
        if json_text.startswith("```"):
            json_text = json_text.split("```")[1]
            if json_text.startswith("json"):
                json_text = json_text[4:]
            json_text = json_text.strip()

        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError as e:
            if len(chain) > 1:
                print(f"   ⚠️ [Intent Router] 模型 '{model}' 返回非 JSON，尝试下一个...")
            continue

        intent = parsed.get("intent", "")
        target_type = parsed.get("target_type", "none")
        confidence = float(parsed.get("confidence", 0))

        if intent not in ALL_INTENTS:
            continue
        if target_type not in ALL_TARGET_TYPES:
            target_type = "none"

        if idx > 0:
            print(f"   ✅ [Intent Router] 模型 '{model}' 重试成功 (链索引 {idx})")

        return {
            "intent": intent,
            "target_type": target_type,
            "confidence": confidence,
            "reasoning": parsed.get("reasoning", ""),
        }

    return None


def get_provider_config(model_name: str) -> Dict:
    model_lower = (model_name or "").lower()

    configs = {
        "qwen": {
            "url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            "model": "qwen3.8-max",
            "auth_key": "DASHSCOPE_API_KEY",
            "format": "openai",
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


def call_provider_for_classify(prompt: str, model_name: str, model_override: str = None, max_timeout: int = 5) -> str:
    import requests
    cfg = get_provider_config(model_name)

    api_format = cfg.get("format", "openai")
    model = model_override if model_override else (cfg["model"]() if callable(cfg["model"]) else cfg["model"])
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

    except Exception as e:
        # ⭐ v4.0: 不再静默吞错——打印诊断信息
        print(f"\n⚠️ [Intent Router] LLM 分类 API 调用失败 ({model_name}/{model}):")
        print(f"   URL: {url}")
        err_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            try:
                err_body = e.response.text[:300] if hasattr(e.response, 'text') else ''
                err_msg += f" | HTTP {e.response.status_code}: {err_body}"
            except Exception:
                pass
        print(f"   错误: {err_msg[:500]}")
        return ""