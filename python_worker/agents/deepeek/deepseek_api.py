# -*- coding: utf-8 -*-
# deepseek_api.py
# ---------------------------------------------------------
# DeepSeek API 调用封装（阿里云 MAAS OpenAI 兼容接口）
# - 主模型: deepseek-v4-pro-0813（via DASHSCOPE_KEY_ACCOUNT_A）
# - 降级模型: deepseek-v4-pro（同 API Key）
# - 旧火山引擎 Ark 保留为兼容回退
# - v3.0 超时时间调整到 300 秒（LLM 处理较慢）
# ---------------------------------------------------------

import requests
import json
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# ============================================================
# 阿里云 MAAS 配置（主）
# ============================================================
MAAS_API_KEY = os.getenv("DEEPSEEK_MAAS_API_KEY") or os.getenv("DASHSCOPE_KEY_ACCOUNT_A")
MAAS_BASE_URL = os.getenv("DEEPSEEK_MAAS_BASE_URL", "https://llm-ithsvxlz15kgi8lc.cn-beijing.maas.aliyuncs.com/compatible-mode/v1")
MAAS_MODEL = os.getenv("DEEPSEEK_MAAS_MODEL", "deepseek-v4-pro-0813")
MAAS_FALLBACK_MODEL = os.getenv("DEEPSEEK_MAAS_FALLBACK_MODEL", "deepseek-v4-pro")

MAAS_URL = MAAS_BASE_URL.rstrip("/")
if not MAAS_URL.endswith("/chat/completions"):
    MAAS_URL += "/chat/completions"

# ============================================================
# 火山引擎 Ark 配置（旧，作为兼容回退）
# ============================================================
VOLC_API_KEY = os.getenv("VOLC_DEEPSEEK_API_KEY") or os.getenv("VOLC_API_KEY")
VOLC_MODEL = os.getenv("VOLC_DEEPSEEK_MODEL", "deepseek-v3-250324")
VOLC_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"


def _post_request(url: str, api_key: str, payload: dict, stream: bool = False, timeout: int = 300):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    if stream:
        full_text = ""
        with requests.post(url, headers=headers, json=payload, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8")
                if decoded.startswith("data: "):
                    data_str = decoded[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        choices = data.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_text += content
                    except json.JSONDecodeError:
                        continue
        return full_text
    else:
        r = requests.post(url, headers=headers, json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        choices = data.get("choices", [])
        if not choices:
            raise ValueError(f"DeepSeek API 返回空响应：{data}")
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if not content:
            raise ValueError(f"DeepSeek API 返回空内容：{data}")
        return content


def _call_maas(prompt: str, stream: bool = False, model: str = None) -> str:
    if not MAAS_API_KEY:
        raise ValueError("DEEPSEEK_MAAS_API_KEY / DASHSCOPE_KEY_ACCOUNT_A 未设置")

    payload = {
        "model": model or MAAS_MODEL,
        "stream": stream,
        "messages": [{"role": "user", "content": prompt}],
    }
    return _post_request(MAAS_URL, MAAS_API_KEY, payload, stream=stream)


def _call_volc(prompt: str, stream: bool = False) -> str:
    if not VOLC_API_KEY:
        raise ValueError("VOLC_DEEPSEEK_API_KEY / VOLC_API_KEY 未设置")

    payload = {
        "model": VOLC_MODEL,
        "stream": stream,
        "messages": [{"role": "user", "content": prompt}],
    }
    return _post_request(VOLC_URL, VOLC_API_KEY, payload, stream=stream)


def call_deepseek(prompt: str, stream: bool = False) -> str:
    """
    调用 DeepSeek API 进行文本生成（自动降级）

    优先级：
      1. 阿里云 MAAS deepseek-v4-pro-0813（主）
      2. 阿里云 MAAS deepseek-v4-pro（降级）
      3. 火山引擎 Ark（兼容回退）

    参数:
        prompt: 提示词字符串
        stream: 是否流式输出（默认 False）

    返回:
        str: LLM 生成的文本响应
    """
    # ---- 尝试 1: MAAS 主模型 ----
    if MAAS_API_KEY:
        try:
            print(f"[DeepSeek] 调用 MAAS 主模型: {MAAS_MODEL}")
            result = _call_maas(prompt, stream=stream, model=MAAS_MODEL)
            return result
        except Exception as e:
            print(f"[DeepSeek] MAAS 主模型 ({MAAS_MODEL}) 失败: {e}")

            # ---- 尝试 2: MAAS 降级模型 ----
            if MAAS_FALLBACK_MODEL and MAAS_FALLBACK_MODEL != MAAS_MODEL:
                try:
                    print(f"[DeepSeek] 降级到 MAAS 备用模型: {MAAS_FALLBACK_MODEL}")
                    result = _call_maas(prompt, stream=stream, model=MAAS_FALLBACK_MODEL)
                    return result
                except Exception as e2:
                    print(f"[DeepSeek] MAAS 降级模型 ({MAAS_FALLBACK_MODEL}) 也失败: {e2}")
            else:
                print("[DeepSeek] 未配置降级模型，跳过")

    # ---- 尝试 3: 火山引擎 Ark（兼容回退）----
    if VOLC_API_KEY:
        try:
            print(f"[DeepSeek] 回退到火山引擎 Ark: {VOLC_MODEL}")
            result = _call_volc(prompt, stream=stream)
            return result
        except Exception as e:
            print(f"[DeepSeek] 火山引擎 Ark 也失败: {e}")

    raise RuntimeError("所有 DeepSeek API 均不可用（MAAS + Volc）")


def call_deepseek_stream(prompt: str):
    """
    流式调用 DeepSeek API（生成器版本）

    优先级与 call_deepseek 相同。

    参数:
        prompt: 提示词字符串

    返回:
        generator: 逐块返回生成的文本
    """
    if not MAAS_API_KEY:
        raise ValueError("DEEPSEEK_MAAS_API_KEY / DASHSCOPE_KEY_ACCOUNT_A 未设置")

    try:
        print(f"[DeepSeek Stream] 调用 MAAS 主模型: {MAAS_MODEL}")
        yield from _stream_maas(prompt, model=MAAS_MODEL)
        return
    except Exception as e:
        print(f"[DeepSeek Stream] MAAS 主模型失败: {e}")

    if MAAS_FALLBACK_MODEL and MAAS_FALLBACK_MODEL != MAAS_MODEL:
        try:
            print(f"[DeepSeek Stream] 降级到: {MAAS_FALLBACK_MODEL}")
            yield from _stream_maas(prompt, model=MAAS_FALLBACK_MODEL)
            return
        except Exception as e2:
            print(f"[DeepSeek Stream] 降级模型也失败: {e2}")

    if VOLC_API_KEY:
        try:
            print(f"[DeepSeek Stream] 回退到火山引擎 Ark")
            yield from _stream_volc(prompt)
            return
        except Exception as e3:
            print(f"[DeepSeek Stream] 火山引擎也失败: {e3}")

    raise RuntimeError("所有 DeepSeek 流式 API 均不可用")


def _stream_maas(prompt: str, model: str = None):
    headers = {
        "Authorization": f"Bearer {MAAS_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model or MAAS_MODEL,
        "stream": True,
        "messages": [{"role": "user", "content": prompt}],
    }
    with requests.post(MAAS_URL, headers=headers, json=payload, stream=True, timeout=300) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8")
            if decoded.startswith("data: "):
                data_str = decoded[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    choices = data.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                except json.JSONDecodeError:
                    continue


def _stream_volc(prompt: str):
    headers = {
        "Authorization": f"Bearer {VOLC_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": VOLC_MODEL,
        "stream": True,
        "messages": [{"role": "user", "content": prompt}],
    }
    with requests.post(VOLC_URL, headers=headers, json=payload, stream=True, timeout=300) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8")
            if decoded.startswith("data: "):
                data_str = decoded[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    choices = data.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                except json.JSONDecodeError:
                    continue