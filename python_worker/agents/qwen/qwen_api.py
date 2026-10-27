# -*- coding: utf-8 -*-
# qwen_api.py
# ---------------------------------------------------------
# Qwen API 调用封装（工业级多模型降级架构）
# - 对齐 DeepSeek deepseek_api.py 的降级模式
# - 模型发现：qwen_model_probe.py 运行时探测 DashScope 可用模型
# - 配置优先：环境变量 QWEN_MODEL / QWEN_FALLBACK_* 覆盖探测结果
# - 所有模型名通过环境变量注入，零硬编码
# ---------------------------------------------------------

import os
import json
import requests
from pathlib import Path
from typing import Generator, Optional, Dict
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from ...worker_config import DASHSCOPE_API_KEY
from .qwen_model_probe import get_text_fallback_chain

DASHSCOPE_TEXT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


def _call_qwen_blocking(prompt: str, model: str, temperature: float = 0.3) -> str:
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    r = requests.post(DASHSCOPE_TEXT_URL, headers=headers, json=body, timeout=300)
    r.raise_for_status()
    data = r.json()
    return _extract_text_from_response(data)


def _call_qwen_sse(prompt: str, model: str, temperature: float = 0.3) -> Generator[str, None, None]:
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "stream": True,
    }
    response = requests.post(
        DASHSCOPE_TEXT_URL, headers=headers, json=body, timeout=300, stream=True
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
                chunk = _extract_text_from_response(data)
                if chunk:
                    yield chunk
            except json.JSONDecodeError:
                continue


def _extract_text_from_response(data: dict) -> str:
    if "choices" in data and len(data["choices"]) > 0:
        choice = data["choices"][0]
        if "delta" in choice and "content" in choice["delta"]:
            return choice["delta"]["content"]
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
# 公共 API（自动降级）
# ============================================================

def call_qwen(prompt: str) -> str:
    """
    调用 Qwen API 进行文本生成（阻塞 + 自动降级）

    降级链来源（按优先级）：
      1. 环境变量 QWEN_MODEL / QWEN_FALLBACK_1 / QWEN_FALLBACK_2 / QWEN_FALLBACK_3
      2. 运行时探测（qwen_model_probe 自动发现 DashScope 可用模型）
      3. 兜底：qwen-turbo
    """
    if not DASHSCOPE_API_KEY:
        raise RuntimeError("DASHSCOPE_API_KEY 未设置")

    chain = get_text_fallback_chain()
    if not chain:
        raise RuntimeError("没有可用的 Qwen 文本模型（探测结果为空且无环境变量配置）")

    last_error = None
    for model in chain:
        try:
            print(f"[Qwen] 调用模型: {model}")
            result = _call_qwen_blocking(prompt, model)
            if model != chain[0]:
                print(f"[Qwen] 降级模型 {model} 调用成功")
            return result
        except Exception as e:
            print(f"[Qwen] 模型 {model} 失败: {e}")
            last_error = e
            continue

    raise RuntimeError(
        f"所有 Qwen 文本模型均不可用 ({', '.join(chain)}): {last_error}"
    )


def call_qwen_stream(prompt: str, temperature: float = 0.3) -> Generator[str, None, None]:
    """
    流式调用 Qwen API（自动降级）

    降级链与 call_qwen 相同。
    """
    if not DASHSCOPE_API_KEY:
        yield f"\n\n[API 调用失败: DASHSCOPE_API_KEY 未设置]"
        return

    chain = get_text_fallback_chain()
    if not chain:
        yield f"\n\n[API 调用失败: 没有可用的 Qwen 模型]"
        return

    last_error = None
    for model in chain:
        try:
            print(f"[Qwen Stream] 调用模型: {model}")
            yield from _call_qwen_sse(prompt, model, temperature)
            if model != chain[0]:
                print(f"[Qwen Stream] 降级模型 {model} 调用成功")
            return
        except Exception as e:
            print(f"[Qwen Stream] 模型 {model} 失败: {e}")
            last_error = e
            continue

    yield f"\n\n[API 调用失败: 所有模型不可用 - {last_error}]"


def call_qwen_with_persona(
    prompt: str,
    persona_config: Optional[Dict] = None,
    use_stream: bool = False,
) -> Generator[str, None, None] | str:
    """
    带人格配置的 Qwen API 调用（自动降级）
    """
    if persona_config:
        system_prompt = persona_config.get("system_prompt", "")
        full_prompt = f"{system_prompt}\n\n---\n\n用户请求:\n{prompt}"
    else:
        full_prompt = prompt

    if use_stream:
        return call_qwen_stream(full_prompt)
    else:
        return call_qwen(full_prompt)