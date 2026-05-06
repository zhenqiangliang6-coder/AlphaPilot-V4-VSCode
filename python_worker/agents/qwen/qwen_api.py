# -*- coding: utf-8 -*-
# qwen_api.py
# ---------------------------------------------------------
# Qwen API 调用封装（支持流式输出）
# ---------------------------------------------------------

import requests
import sys
import os
from typing import Generator

# 添加父目录到路径，以便导入 worker_config
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ...worker_config import DASHSCOPE_API_KEY   # ★ 正确的相对导入


def call_qwen(prompt: str) -> str:
    """
    调用 Qwen API 进行文本生成（阻塞模式）
    
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
    
    r = requests.post(url, headers=headers, json=body, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data["output"]["text"]


def call_qwen_stream(prompt: str) -> Generator[str, None, None]:
    """
    ⭐ 新增：流式调用 Qwen API（逐 token 返回）
    
    参数:
        prompt: 提示词字符串
    
    返回:
        Generator[str, None, None]: 逐块返回生成的文本
    
    使用示例:
        for chunk in call_qwen_stream("写一个函数"):
            print(chunk, end='', flush=True)
    
    异常:
        requests.RequestException: 当 API 调用失败时抛出
    """
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
        "X-DashScope-SSE": "enable"  # ⭐ 启用 SSE 流式输出
    }
    body = {
        "model": "qwen-turbo",
        "input": {"prompt": prompt},
        "parameters": {
            "incremental_output": True  # ⭐ 增量输出模式
        }
    }
    
    try:
        # 使用 stream=True 启用流式请求
        response = requests.post(
            url, 
            headers=headers, 
            json=body, 
            timeout=60,
            stream=True
        )
        response.raise_for_status()
        
        # 解析 SSE (Server-Sent Events) 格式
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            
            # SSE 格式: "data: {...}"
            if line.startswith('data:'):
                data_str = line[5:].strip()
                
                # 检查是否是结束标记
                if data_str == '[DONE]':
                    break
                
                try:
                    import json
                    data = json.loads(data_str)
                    
                    # 提取文本内容
                    if 'output' in data and 'text' in data['output']:
                        chunk = data['output']['text']
                        yield chunk
                        
                except json.JSONDecodeError as e:
                    print(f"[WARN] JSON 解析失败: {e}, 原始数据: {data_str}")
                    continue
                    
    except Exception as e:
        print(f"[ERROR] 流式 API 调用失败: {e}")
        # 降级：返回错误信息而非抛出异常
        yield f"\n\n[API 调用失败: {str(e)}]"
