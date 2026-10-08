# -*- coding: utf-8 -*-
# maas_api.py
# ---------------------------------------------------------
# MaaS (混元) API 调用封装（腾讯混元平台）
# - 超时时间调整到 300 秒（LLM 处理较慢）
# ---------------------------------------------------------

import requests
import json
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / '.env')

# MaaS 混元 API 配置
MAAS_API_KEY = os.getenv("TENCENT_MAAS_API_KEY") or os.getenv("TENCENT_MaaS_API_KEY")
MAAS_MODEL = os.getenv("TENCENT_MAAS_MODEL", os.getenv("MAAS_MODEL", "hy4-preview"))
MAAS_BASE_URL = os.getenv("TENCENT_MAAS_BASE_URL", os.getenv("MAAS_URL", "https://tokenhub.tencentmaas.com/v1"))
MAAS_URL = MAAS_BASE_URL.rstrip("/")
if not MAAS_URL.endswith("/chat/completions"):
    MAAS_URL += "/chat/completions"


def call_maas(prompt: str, stream: bool = False) -> str:
    """
    调用 MaaS 混元 API 进行文本生成
    
    参数:
        prompt: 提示词字符串
        stream: 是否流式输出（默认 False）
    
    返回:
        str: LLM 生成的文本响应
    
    异常:
        requests.RequestException: 当 API 调用失败时抛出
        ValueError: 当 API Key 未设置时抛出
    """
    if not MAAS_API_KEY:
        raise ValueError("MAAS_API_KEY 未设置（请检查 .env 文件）")
    
    headers = {
        "Authorization": f"Bearer {MAAS_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MAAS_MODEL,
        "stream": stream,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }
    
    if stream:
        # 流式模式
        full_text = ""
        with requests.post(MAAS_URL, headers=headers, json=payload, stream=True, timeout=300) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                
                decoded = line.decode('utf-8')
                
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
        # 非流式模式
        r = requests.post(MAAS_URL, headers=headers, json=payload, timeout=300)
        r.raise_for_status()
        data = r.json()
        
        # 提取响应内容
        choices = data.get("choices", [])
        if not choices:
            raise ValueError(f"MaaS API 返回空响应：{data}")
        
        message = choices[0].get("message", {})
        content = message.get("content", "")
        
        if not content:
            raise ValueError(f"MaaS API 返回空内容：{data}")
        
        return content


def call_maas_stream(prompt: str):
    """
    流式调用 MaaS 混元 API（生成器版本）
    
    参数:
        prompt: 提示词字符串
    
    返回:
        generator: 逐块返回生成的文本
    
    使用示例:
        for chunk in call_maas_stream("你的提示词"):
            print(chunk, end='', flush=True)
    """
    if not MAAS_API_KEY:
        raise ValueError("MAAS_API_KEY 未设置（请检查 .env 文件）")
    
    headers = {
        "Authorization": f"Bearer {MAAS_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MAAS_MODEL,
        "stream": True,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }
    
    with requests.post(MAAS_URL, headers=headers, json=payload, stream=True, timeout=300) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            
            decoded = line.decode('utf-8')
            
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
