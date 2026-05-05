# -*- coding: utf-8 -*-
# doubao_api.py
# ---------------------------------------------------------
# 火山引擎豆包大模型 API 调用封装
# - 支持多模态输入（图片 + 文本）
# - Responses API 格式
# ---------------------------------------------------------

import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

# API 配置
DOUBAO_API_KEY = os.getenv("VOLC_API_KEY")
MODEL_NAME = "doubao-seed-2-0-lite-260215"
BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/responses"


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
    
    # 发送请求
    response = requests.post(BASE_URL, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    
    # 解析响应
    result = response.json()
    
    # 提取响应内容（根据实际 API 返回结构调整）
    # 注意：这里需要根据豆包 API 的实际返回格式进行调整
    # 以下是假设的格式，需要根据实际情况修改
    if "output" in result:
        output = result["output"]
        if "text" in output:
            return output["text"]
        elif "choices" in output:
            choices = output["choices"]
            if choices and len(choices) > 0:
                return choices[0].get("message", {}).get("content", "")
    
    # 备用提取路径
    if "choices" in result:
        choices = result["choices"]
        if choices and len(choices) > 0:
            return choices[0].get("message", {}).get("content", "")
    
    # 如果都无法提取，返回整个结果（用于调试）
    return json.dumps(result, ensure_ascii=False)


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
    
    with requests.post(BASE_URL, headers=headers, json=payload, stream=True, timeout=120) as response:
        response.raise_for_status()
        
        for line in response.iter_lines():
            if not line:
                continue
            
            decoded = line.decode('utf-8')
            
            if decoded.startswith("data: "):
                data_str = decoded[6:]
                if data_str.strip() == "[DONE]":
                    break
                
                try:
                    data = json.loads(data_str)
                    # 根据实际格式提取内容
                    if "output" in data:
                        output = data["output"]
                        if "text" in output:
                            yield output["text"]
                        elif "choices" in output:
                            choices = output["choices"]
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                except json.JSONDecodeError:
                    continue
