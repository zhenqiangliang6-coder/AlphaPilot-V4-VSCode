# -*- coding: utf-8 -*-
# deepseek_api.py
# ---------------------------------------------------------
# DeepSeek API 调用封装（火山引擎 Ark 平台）
# ---------------------------------------------------------

import requests
import sys
import os
from dotenv import load_dotenv

load_dotenv()

# 优先读取专用 Key，如果没有则读取通用 Key
DEEPSEEK_API_KEY = os.getenv("VOLC_DEEPSEEK_API_KEY") or os.getenv("VOLC_API_KEY")
MODEL_NAME = os.getenv("VOLC_DEEPSEEK_MODEL", "deepseek-v3-250324")
URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"


def call_deepseek(prompt: str, stream: bool = False) -> str:
    """
    调用 DeepSeek API 进行文本生成
    
    参数:
        prompt: 提示词字符串
        stream: 是否流式输出（默认 False）
    
    返回:
        str: LLM 生成的文本响应
    
    异常:
        requests.RequestException: 当 API 调用失败时抛出
        ValueError: 当 API Key 未设置时抛出
    """
    if not DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY 未设置（请检查 .env 文件）")
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODEL_NAME,
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
        with requests.post(URL, headers=headers, json=payload, stream=True, timeout=120) as r:
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
        r = requests.post(URL, headers=headers, json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()
        
        # 提取响应内容
        choices = data.get("choices", [])
        if not choices:
            raise ValueError(f"DeepSeek API 返回空响应：{data}")
        
        message = choices[0].get("message", {})
        content = message.get("content", "")
        
        if not content:
            raise ValueError(f"DeepSeek API 返回空内容：{data}")
        
        return content
