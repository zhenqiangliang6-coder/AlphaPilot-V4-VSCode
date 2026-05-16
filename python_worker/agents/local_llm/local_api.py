# -*- coding: utf-8 -*-
# local_api.py
# ---------------------------------------------------------
# Local LLM (LM Studio) API 调用封装
# - 支持流式和非流式输出
# - 使用 OpenAI 兼容格式 /v1/chat/completions
# ---------------------------------------------------------

import requests
import json
from worker_config import NODE_API_URL
import os


# =========================
# 配置项（从 .env 统一配置中心读取）
# =========================

LOCAL_MODEL_NAME = os.getenv("LOCAL_LLM_MODEL", "google/gemma-4-e4b")  # LM Studio 模型名称
LLM_API_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:1234/v1")  # LM Studio API 端点


def call_local_llm(prompt: str, model: str = None, stream: bool = False, task_id: str = None) -> str:
    """
    调用本地 LLM (LM Studio) API - OpenAI 兼容格式
    
    参数:
        prompt: 提示词字符串
        model: 模型名称（默认使用 LOCAL_MODEL_NAME）
        stream: 是否启用流式输出
        task_id: 任务 ID（用于流式输出时通知前端）
    
    返回:
        str: LLM 生成的文本响应
    
    异常:
        requests.RequestException: 当 API 调用失败时抛出
    """
    if model is None:
        model = LOCAL_MODEL_NAME
    
    # ⭐ LM Studio 使用 OpenAI 兼容格式
    url = f"{LLM_API_BASE_URL}/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        # LM Studio 不需要 API Key，但某些实现可能需要
        "Authorization": "Bearer not-needed"
    }
    
    body = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": stream,
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 4096
    }
    
    try:
        if stream and task_id:
            # 流式模式：逐块接收并推送给前端
            return _call_streaming(url, headers, body, task_id)
        else:
            # 非流式模式：一次性接收完整响应
            response = requests.post(url, headers=headers, json=body, timeout=120)
            response.raise_for_status()
            
            data = response.json()
            
            # ⭐ OpenAI 兼容格式响应
            if "choices" in data and len(data["choices"]) > 0:
                choice = data["choices"][0]["message"]
                
                #  兼容处理：某些模型（如 Gemma）会把内容放在 reasoning_content
                content = choice.get("content", "")
                reasoning = choice.get("reasoning_content", "")
                
                # 优先使用 content，如果为空则使用 reasoning_content
                if not content and reasoning:
                    return reasoning
                return content
            else:
                raise ValueError(f"未知的响应格式: {data.keys()}")
    
    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            f"无法连接到 LM Studio 服务 ({LLM_API_BASE_URL})。\n"
            f"请确保 LM Studio 已启动并运行在 {LLM_API_BASE_URL}\n"
            f"💡 提示：在 LM Studio 中启动 Server 模式"
        )
    except requests.exceptions.Timeout:
        raise TimeoutError(f"LM Studio API 调用超时（120秒）")
    except Exception as e:
        raise RuntimeError(f"Local LLM API 调用失败: {str(e)}")


def _call_streaming(url: str, headers: dict, body: dict, task_id: str) -> str:
    """
    流式调用本地 LLM (LM Studio)，实时推送内容到前端
    
    参数:
        url: API URL
        headers: 请求头
        body: 请求体
        task_id: 任务 ID
    
    返回:
        str: 完整的响应文本
    """
    from worker_config import stream_start, stream_chunk, stream_end
    
    full_response = ""
    
    try:
        # 发送流式开始信号
        stream_start(task_id, title=" Local LLM 正在生成...")
        
        # 发起流式请求
        with requests.post(url, headers=headers, json=body, stream=True, timeout=120) as response:
            response.raise_for_status()
            
            # ⭐ LM Studio 使用 SSE (Server-Sent Events) 格式
            for line in response.iter_lines():
                if not line:
                    continue
                
                line_str = line.decode('utf-8')
                
                # SSE 格式：data: {...}
                if line_str.startswith("data: "):
                    data_str = line_str[6:]  # 去掉 "data: " 前缀
                    
                    if data_str == "[DONE]":
                        # 流式结束标记
                        break
                    
                    try:
                        chunk_data = json.loads(data_str)
                        
                        #  OpenAI 兼容格式：delta.content 或 delta.reasoning_content
                        if "choices" in chunk_data and len(chunk_data["choices"]) > 0:
                            delta = chunk_data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            reasoning = delta.get("reasoning_content", "")
                            
                            # 优先使用 content，如果为空则使用 reasoning_content
                            token = content if content else reasoning
                            
                            if token:
                                full_response += token
                                
                                # 推送流式片段到前端
                                stream_chunk(task_id, token)

                    except json.JSONDecodeError:
                        continue
        
        # 发送流式结束信号
        stream_end(task_id)
        
        return full_response
    
    except Exception as e:
        from worker_config import stream_error
        stream_error(task_id, f"流式输出失败: {str(e)}")
        raise


def test_connection() -> bool:
    """
    测试 LM Studio 连接是否正常
    
    返回:
        bool: True 表示连接成功，False 表示失败
    """
    try:
        # ⭐ LM Studio 使用 /v1/models 端点
        url = f"{LLM_API_BASE_URL}/models"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        
        models = response.json().get("data", [])
        model_names = [m["id"] for m in models]
        print(f"✅ LM Studio 连接成功，可用模型: {model_names}")
        return True
    
    except Exception as e:
        print(f" LM Studio 连接失败: {e}")
        print(f"💡 请确保：")
        print(f"   1. LM Studio 已启动")
        print(f"   2. Server 模式已开启")
        print(f"   3. API 地址正确: {LLM_API_BASE_URL}")
        return False


if __name__ == "__main__":
    # 测试连接
    print("🔍 测试 LM Studio 连接...")
    if test_connection():
        print("\n💬 发送测试消息...")
        result = call_local_llm("你好，请介绍一下你自己。")
        print(f"\n📝 响应:\n{result}")
    else:
        print("\n⚠️ 请先启动 LM Studio 服务")
