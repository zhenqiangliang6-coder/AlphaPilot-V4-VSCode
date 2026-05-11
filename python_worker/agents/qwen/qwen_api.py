# -*- coding: utf-8 -*-
# qwen_api.py
# ---------------------------------------------------------
# Qwen API 调用封装（支持流式输出 + 人格配置）
# ---------------------------------------------------------

import requests
import sys
import os
from typing import Generator, Optional, Dict

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


# =========================
# ⭐ v2.6 新增：支持人格配置的 API 调用
# =========================

def call_qwen_with_persona(
    prompt: str, 
    persona_config: Optional[Dict] = None,
    use_stream: bool = False
) -> Generator[str, None, None] | str:
    """
    ⭐ v2.6 新增：带人格配置的 Qwen API 调用
    
    参数:
        prompt: 用户提示词
        persona_config: 人格配置字典 (包含 system_prompt, tone 等)
        use_stream: 是否使用流式输出
        
    返回:
        如果 use_stream=False: str (完整响应)
        如果 use_stream=True: Generator[str, None, None] (流式响应)
    
    使用示例:
        # 非流式
        from .personas import get_persona_config
        persona = get_persona_config("engineer")
        result = call_qwen_with_persona("写一个排序算法", persona, use_stream=False)
        
        # 流式
        for chunk in call_qwen_with_persona("写一首诗", persona, use_stream=True):
            print(chunk, end='', flush=True)
    """
    # 构建完整的 System Prompt
    if persona_config:
        system_prompt = persona_config.get("system_prompt", "")
        full_prompt = f"{system_prompt}\n\n---\n\n用户请求:\n{prompt}"
    else:
        full_prompt = prompt
    
    # 根据是否流式选择不同的调用方式
    if use_stream:
        return _call_qwen_stream_internal(full_prompt)
    else:
        return _call_qwen_blocking_internal(full_prompt)


def _call_qwen_blocking_internal(prompt: str) -> str:
    """内部阻塞调用函数"""
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    headers = {"Authorization": f"Bearer {DASHSCOPE_API_KEY}"}
    body = {
        "model": "qwen-turbo",
        "input": {"prompt": prompt}
    }
    
    try:
        r = requests.post(url, headers=headers, json=body, timeout=60)
        r.raise_for_status()
        data = r.json()
        return data["output"]["text"]
    except Exception as e:
        print(f"[ERROR] Qwen API 调用失败: {e}")
        return f"\n\n[API 调用失败: {str(e)}]"


def _call_qwen_stream_internal(prompt: str) -> Generator[str, None, None]:
    """内部流式调用函数"""
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
        "X-DashScope-SSE": "enable"
    }
    body = {
        "model": "qwen-turbo",
        "input": {"prompt": prompt},
        "parameters": {
            "incremental_output": True
        }
    }
    
    try:
        response = requests.post(
            url, 
            headers=headers, 
            json=body, 
            timeout=120,
            stream=True
        )
        response.raise_for_status()
        
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            
            if line.startswith('data:'):
                data_str = line[5:].strip()
                
                if data_str == '[DONE]':
                    break
                
                try:
                    import json
                    data = json.loads(data_str)
                    
                    if 'output' in data and 'text' in data['output']:
                        chunk = data['output']['text']
                        yield chunk
                        
                except json.JSONDecodeError as e:
                    print(f"[WARN] JSON 解析失败: {e}")
                    continue
                    
    except Exception as e:
        print(f"[ERROR] 流式 API 调用失败: {e}")
        yield f"\n\n[API 调用失败: {str(e)}]"
