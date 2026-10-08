# -*- coding: utf-8 -*-
# step_executor/qwen_api.py
# ---------------------------------------------------------
# Qwen API 调用封装
# - ⭐ v2.7 超时时间调整到 300 秒（LLM 处理较慢）
# ---------------------------------------------------------

import requests
from worker_config import DASHSCOPE_API_KEY


def call_qwen(prompt: str) -> str:
    """
    调用 Qwen API 进行文本生成
    
    参数:
        prompt: 提示词字符串
    
    返回:
        str: LLM 生成的文本响应
    
    异常:
        requests.RequestException: 当 API 调用失败时抛出
    """
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    headers = {"Authorization": f"Bearer {DASHSCOPE_API_KEY}"}
    body = {
        "model": "qwen-turbo",
        "input": {"prompt": prompt}
    }
    
    r = requests.post(url, headers=headers, json=body, timeout=300)
    r.raise_for_status()
    data = r.json()
    return data["output"]["text"]
