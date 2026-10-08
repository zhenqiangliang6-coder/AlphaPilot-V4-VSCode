# -*- coding: utf-8 -*-
# gemini_api.py
# ---------------------------------------------------------
# Google Gemini 原生 API 调用封装（通过 AlphaPilot International Proxy）
# - 使用 Gemini 原生接口格式（非 OpenAI 兼容）
# - 支持阻塞模式 + 流式输出 + 人格配置
# - ⭐ 超时时间 300 秒（与 Qwen Worker 保持一致）
# ---------------------------------------------------------

import json
import requests
import sys
import os
from typing import Generator, Optional, Dict

# 添加父目录到路径，以便导入 worker_config
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from ...worker_config import (
    GEMINI_PROXY_URL,
    GEMINI_MODEL,
    GEMINI_TIMEOUT,
    GEMINI_MAX_OUTPUT_TOKENS,
    GEMINI_TEMPERATURE,
)


# =========================================================
# 核心 API 调用函数
# =========================================================

def call_gemini(prompt: str, model: str = None) -> str:
    """
    调用 Google Gemini API 进行文本生成（阻塞模式）
    
    通过 AlphaPilot International Proxy 转发到 Google Gemini。
    使用原生 Gemini API 格式。
    
    参数:
        prompt: 提示词字符串
        model: 模型名称（默认使用 GEMINI_MODEL 配置）
    
    返回:
        str: LLM 生成的文本响应
    
    异常:
        requests.RequestException: 当 API 调用失败时抛出
    """
    model = model or GEMINI_MODEL
    
    url = f"{GEMINI_PROXY_URL}/gemini/v1beta/models/{model}:generateContent"
    headers = {
        "Content-Type": "application/json"
    }
    
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": GEMINI_TEMPERATURE,
            "maxOutputTokens": GEMINI_MAX_OUTPUT_TOKENS,
        }
    }
    
    r = requests.post(url, headers=headers, json=body, timeout=GEMINI_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    
    # 解析 Gemini 原生响应格式
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ValueError(f"Gemini API 响应格式异常: {e}, 原始响应: {json.dumps(data, ensure_ascii=False)[:500]}")


def call_gemini_stream(prompt: str, model: str = None) -> Generator[str, None, None]:
    """
    ⭐ 流式调用 Google Gemini API（逐 token 返回）
    
    通过 AlphaPilot International Proxy 的 streamGenerateContent 端点。
    
    参数:
        prompt: 提示词字符串
        model: 模型名称（默认使用 GEMINI_MODEL 配置）
    
    返回:
        Generator[str, None, None]: 逐块返回生成的文本
    
    使用示例:
        for chunk in call_gemini_stream("写一个函数"):
            print(chunk, end='', flush=True)
    """
    model = model or GEMINI_MODEL
    
    url = f"{GEMINI_PROXY_URL}/gemini/v1beta/models/{model}:streamGenerateContent"
    headers = {
        "Content-Type": "application/json"
    }
    
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": GEMINI_TEMPERATURE,
            "maxOutputTokens": GEMINI_MAX_OUTPUT_TOKENS,
        }
    }
    
    try:
        response = requests.post(
            url,
            headers=headers,
            json=body,
            timeout=GEMINI_TIMEOUT,
            stream=True
        )
        response.raise_for_status()
        
        # 解析流式响应（SSE 格式或 JSON 数组）
        buffer = ""
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            
            # 处理 SSE 格式: "data: {...}"
            if line.startswith('data:'):
                data_str = line[5:].strip()
                if data_str == '[DONE]':
                    break
                try:
                    data = json.loads(data_str)
                    text = _extract_text_from_response(data)
                    if text:
                        yield text
                except json.JSONDecodeError:
                    continue
            else:
                # 尝试直接解析为 JSON（某些代理返回纯 JSON 数组）
                buffer += line
                try:
                    data = json.loads(buffer)
                    text = _extract_text_from_response(data)
                    if text:
                        yield text
                    buffer = ""
                except json.JSONDecodeError:
                    continue
                    
    except Exception as e:
        print(f"[ERROR] Gemini 流式 API 调用失败: {e}")
        yield f"\n\n[API 调用失败: {str(e)}]"


def call_gemini_with_persona(
    prompt: str,
    persona_config: Optional[Dict] = None,
    use_stream: bool = False,
    model: str = None
) -> Generator[str, None, None] | str:
    """
    ⭐ 带人格配置的 Gemini API 调用
    
    参数:
        prompt: 用户提示词
        persona_config: 人格配置字典 (包含 system_prompt, tone 等)
        use_stream: 是否使用流式输出
        model: 模型名称
    
    返回:
        如果 use_stream=False: str (完整响应)
        如果 use_stream=True: Generator[str, None, None] (流式响应)
    """
    # 构建完整的 System Prompt
    if persona_config:
        system_prompt = persona_config.get("system_prompt", "")
        full_prompt = f"{system_prompt}\n\n---\n\n用户请求:\n{prompt}"
    else:
        full_prompt = prompt
    
    # 根据是否流式选择不同的调用方式
    if use_stream:
        return _call_gemini_stream_internal(full_prompt, model)
    else:
        return _call_gemini_blocking_internal(full_prompt, model)


# =========================================================
# 内部实现函数
# =========================================================

def _call_gemini_blocking_internal(prompt: str, model: str = None) -> str:
    """内部阻塞调用函数"""
    model = model or GEMINI_MODEL
    
    url = f"{GEMINI_PROXY_URL}/gemini/v1beta/models/{model}:generateContent"
    headers = {
        "Content-Type": "application/json"
    }
    
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": GEMINI_TEMPERATURE,
            "maxOutputTokens": GEMINI_MAX_OUTPUT_TOKENS,
        }
    }
    
    try:
        r = requests.post(url, headers=headers, json=body, timeout=GEMINI_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"[ERROR] Gemini API 调用失败: {e}")
        return f"\n\n[API 调用失败: {str(e)}]"


def _call_gemini_stream_internal(prompt: str, model: str = None) -> Generator[str, None, None]:
    """内部流式调用函数"""
    model = model or GEMINI_MODEL
    
    url = f"{GEMINI_PROXY_URL}/gemini/v1beta/models/{model}:streamGenerateContent"
    headers = {
        "Content-Type": "application/json"
    }
    
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": GEMINI_TEMPERATURE,
            "maxOutputTokens": GEMINI_MAX_OUTPUT_TOKENS,
        }
    }
    
    try:
        response = requests.post(
            url,
            headers=headers,
            json=body,
            timeout=GEMINI_TIMEOUT,
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
                    text = _extract_text_from_response(data)
                    if text:
                        yield text
                except json.JSONDecodeError:
                    continue
            else:
                buffer += line
                try:
                    data = json.loads(buffer)
                    text = _extract_text_from_response(data)
                    if text:
                        yield text
                    buffer = ""
                except json.JSONDecodeError:
                    continue
                    
    except Exception as e:
        print(f"[ERROR] Gemini 流式 API 调用失败: {e}")
        yield f"\n\n[API 调用失败: {str(e)}]"


def _extract_text_from_response(data: dict) -> str:
    """
    从 Gemini 原生响应中提取文本内容
    
    支持多种响应格式：
    - 标准格式: {"candidates": [{"content": {"parts": [{"text": "..."}]}}]}
    - 流式块格式: 同上但可能只有部分文本
    """
    try:
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        
        if not parts:
            return ""
        
        return parts[0].get("text", "")
    except (KeyError, IndexError, TypeError):
        return ""
