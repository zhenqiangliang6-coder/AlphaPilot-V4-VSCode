# -*- coding: utf-8 -*-
# doubao_api.py
# ---------------------------------------------------------
# 火山引擎豆包大模型 API 调用封装
# - 支持多模态输入（图片 + 文本）
# - Responses API 格式
# - ⭐ v2.7 超时时间调整到 300 秒（LLM 处理较慢）
# ---------------------------------------------------------

import requests
import json
import os
import time
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

# API 配置
DOUBAO_API_KEY = os.getenv("VOLC_API_KEY")
MODEL_NAME = "doubao-seed-2-0-lite-260215"
BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/responses"


def _create_session_with_retry():
    """
    创建带有重试机制的 Session，并禁用代理（解决 ProxyError）
    """
    session = requests.Session()
    
    # ⭐ 配置重试策略：最多重试 3 次，每次间隔递增
    retry_strategy = Retry(
        total=3,
        backoff_factor=2,  # 第1次等2秒，第2次等4秒，第3次等8秒
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"]
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    # ⭐ 关键修复：禁用所有代理（解决 ProxyError）
    session.trust_env = False  # 忽略系统环境变量中的代理设置
    session.proxies = {'http': None, 'https': None}  # 显式禁用代理
    
    return session


def call_doubao(prompt: str, image_url: str = None) -> str:
    """
    调用豆包大模型 API 进行文本生成
    
    参数:
        prompt: 提示词字符串
        image_url: 可选的图片 URL（用于多模态输入）
    
    返回:
        str: LLM 生成的文本响应
    
    异常:
        requests.RequestException: 当 API 调用失败时抛出
        ValueError: 当 API Key 未设置时抛出
    """
    if not DOUBAO_API_KEY:
        raise ValueError("DOUBAO_API_KEY 未设置（请检查 .env 文件）")
    
    headers = {
        "Authorization": f"Bearer {DOUBAO_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 构建 input 数组
    content_list = []
    
    # 如果有图片，添加图片输入
    if image_url:
        content_list.append({
            "type": "input_image",
            "image_url": image_url
        })
    
    # 添加文本输入
    content_list.append({
        "type": "input_text",
        "text": prompt
    })
    
    payload = {
        "model": MODEL_NAME,
        "input": [
            {
                "role": "user",
                "content": content_list
            }
        ]
    }
    
    # ⭐ 使用带重试机制的 Session（已禁用代理）
    session = _create_session_with_retry()
    
    try:
        # 发送请求
        response = session.post(BASE_URL, headers=headers, json=payload, timeout=300)
        response.raise_for_status()
        
        # 解析响应
        result = response.json()
        
        # ⭐ 提取响应内容（根据火山引擎 Responses API 格式）
        if "output" in result and isinstance(result["output"], list):
            output_list = result["output"]
            if output_list and len(output_list) > 0:
                first_output = output_list[0]
                
                # 尝试从 summary 中提取文本（火山引擎格式）
                if "summary" in first_output:
                    summary_list = first_output["summary"]
                    if summary_list and len(summary_list) > 0:
                        for item in summary_list:
                            if item.get("type") == "summary_text":
                                text_content = item.get("text", "")
                                if text_content:
                                    return text_content
                
                # 尝试从 content 中提取文本（备用格式）
                if "content" in first_output:
                    content_list = first_output["content"]
                    if content_list and len(content_list) > 0:
                        text_content = content_list[0].get("text", "")
                        if text_content:
                            return text_content
        
        # 备用路径：尝试 choices 格式
        if "choices" in result:
            choices = result["choices"]
            if choices and len(choices) > 0:
                return choices[0].get("message", {}).get("content", "")
        
        # 如果都无法提取，记录警告并返回空
        print(f"[WARN] Doubao API 返回格式无法解析: {json.dumps(result, ensure_ascii=False)[:500]}")
        return ""
        
    except requests.RequestException as e:
        print(f"[ERROR] Doubao API 调用失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"[ERROR] HTTP 状态码: {e.response.status_code}")
            print(f"[ERROR] 响应内容: {e.response.text[:500]}")
        raise
    finally:
        session.close()  # 确保关闭 Session


def call_doubao_stream(prompt: str, image_url: str = None):
    """
    流式调用豆包大模型 API（如果支持）
    
    参数:
        prompt: 提示词字符串
        image_url: 可选的图片 URL
    
    Yields:
        str: 逐块返回生成的文本
    """
    if not DOUBAO_API_KEY:
        raise ValueError("DOUBAO_API_KEY 未设置")
    
    headers = {
        "Authorization": f"Bearer {DOUBAO_API_KEY}",
        "Content-Type": "application/json"
    }
    
    content_list = []
    
    if image_url:
        content_list.append({
            "type": "input_image",
            "image_url": image_url
        })
    
    content_list.append({
        "type": "input_text",
        "text": prompt
    })
    
    payload = {
        "model": MODEL_NAME,
        "input": [
            {
                "role": "user",
                "content": content_list
            }
        ],
        "stream": True  # 启用流式
    }
    
    # ⭐ 使用带重试机制的 Session（已禁用代理）
    session = _create_session_with_retry()
    
    try:
        with session.post(BASE_URL, headers=headers, json=payload, stream=True, timeout=300) as response:
            response.raise_for_status()
            
            for line in response.iter_lines():
                if not line:
                    continue
                
                decoded = line.decode('utf-8')
                
                # 处理 SSE 格式
                if decoded.startswith("data: "):
                    data_str = decoded[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    
                    try:
                        data = json.loads(data_str)
                        
                        # ⭐ 火山引擎 Responses API 流式格式
                        if "output" in data and isinstance(data["output"], list):
                            output_list = data["output"]
                            if output_list and len(output_list) > 0:
                                first_output = output_list[0]
                                
                                # 尝试从 summary 中提取文本（火山引擎格式）
                                if "summary" in first_output:
                                    summary_list = first_output["summary"]
                                    if summary_list and len(summary_list) > 0:
                                        for item in summary_list:
                                            if item.get("type") == "summary_text":
                                                text_content = item.get("text", "")
                                                if text_content:
                                                    yield text_content
                                
                                # 尝试从 content 中提取文本（备用格式）
                                elif "content" in first_output:
                                    content_list = first_output["content"]
                                    if content_list and len(content_list) > 0:
                                        text_content = content_list[0].get("text", "")
                                        if text_content:
                                            yield text_content
                        
                        # 备用路径：delta 格式
                        elif "choices" in data:
                            choices = data["choices"]
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                                    
                    except json.JSONDecodeError:
                        continue
                        
    except requests.RequestException as e:
        print(f"[ERROR] Doubao 流式 API 调用失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"[ERROR] HTTP 状态码: {e.response.status_code}")
        raise
    finally:
        session.close()  # 确保关闭 Session
