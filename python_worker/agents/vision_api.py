# -*- coding: utf-8 -*-
# agents/vision_api.py
# AlphaPilot 统一多模态视觉 API 调用层
# 输入: prompt + images[], 输出: 归一化文本响应
# 自动模型路由, 不支持的模型降级到 Qwen
# ⭐ v4.3: Qwen 视觉模型通过 qwen_model_probe 运行时探测 + 环境变量降级

import base64
import os
import json
import requests
from typing import List, Dict, Optional

from ..worker_config import DASHSCOPE_API_KEY

SUPPORTED_VISION_MODELS = {"qwen", "doubao", "gemini"}
DEEPSEEK_NON_VISION = {"deepseek"}

VISION_SYSTEM_PROMPT = (
    "你是一个专业的图像分析助手。"
    "当用户提供图片时，请仔细观察图片内容，结合用户的问题给出准确的分析。"
    "如果图片包含代码、错误信息、UI 界面等，请从编程角度分析。"
    "如果图片包含图表、数据，请提取关键信息。"
    "如果图片是设计稿或原型图，请描述布局结构并给出实现建议。"
    "禁止提及你无法看到图片，你已经收到了图片数据。"
)


def has_vision_support(task_payload: dict) -> bool:
    images = task_payload.get("images", [])
    return isinstance(images, list) and len(images) > 0


def read_images_from_workspace(
    images: List[dict], workspace_root: str
) -> List[dict]:
    result = []
    for img in images:
        img_path = img.get("path", "")
        if not img_path:
            continue
        full_path = os.path.join(workspace_root, img_path)
        if not os.path.isfile(full_path):
            continue
        with open(full_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
        result.append({
            "name": img.get("name", os.path.basename(img_path)),
            "base64": b64_data,
            "mime": "image/jpeg",
        })
    return result


def call_vision(prompt: str, images: List[dict], model_type: str) -> str:
    if not images:
        return "[Vision] 未提供图片数据"

    model_lower = model_type.lower()

    if "qwen" in model_lower:
        return _call_qwen_vision(prompt, images)
    elif "doubao" in model_lower:
        return _call_doubao_vision(prompt, images)
    elif "gemini" in model_lower:
        return _call_gemini_vision(prompt, images)

    return _call_qwen_vision(prompt, images)


def _call_qwen_vision(prompt: str, images: List[dict]) -> str:
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }

    content_list = []
    for img in images:
        content_list.append({
            "type": "image_url",
            "image_url": {
                "url": (
                    f"data:{img.get('mime', 'image/jpeg')};base64,"
                    f"{img['base64']}"
                )
            },
        })
    content_list.append({"type": "text", "text": prompt})

    from .qwen.qwen_model_probe import get_vision_fallback_chain
    vision_chain = get_vision_fallback_chain()

    last_error = None
    for model in vision_chain:
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {"role": "user", "content": content_list},
            ],
            "temperature": 0.3,
        }

        try:
            print(f"[Qwen Vision] 调用模型: {model}")
            r = requests.post(url, headers=headers, json=body, timeout=300)
            r.raise_for_status()
            data = r.json()

            choices = data.get("choices", [])
            if choices and len(choices) > 0:
                msg = choices[0].get("message", {})
                content = msg.get("content", "")
                if isinstance(content, list):
                    texts = [
                        item.get("text", "")
                        for item in content
                        if isinstance(item, dict) and item.get("text")
                    ]
                    return "\n".join(texts)
                if content:
                    if model != vision_chain[0]:
                        print(f"[Qwen Vision] 降级模型 {model} 调用成功")
                    return content

            print(f"[Qwen Vision] 模型 {model} 返回空内容，尝试下一个...")
            last_error = ValueError(f"模型 {model} 返回空内容")

        except requests.RequestException as e:
            print(f"[Qwen Vision] 模型 {model} 失败: {e}")
            last_error = e
            continue

    return f"[Vision] 所有 Qwen 视觉模型均不可用 ({', '.join(vision_chain)}): {last_error}"


def _call_doubao_vision(prompt: str, images: List[dict]) -> str:
    from .Volcengine.doubao_api import _create_session_with_retry

    api_key = os.getenv("DOUBAO_API_KEY", "")
    if not api_key:
        return "[Vision] DOUBAO_API_KEY 未设置"

    model_name = os.getenv("DOUBAO_MODEL_NAME", "doubao-pro-32k")
    url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

    content_list = []
    for img in images:
        content_list.append({
            "type": "image_url",
            "image_url": {
                "url": (
                    f"data:{img.get('mime', 'image/jpeg')};base64,"
                    f"{img['base64']}"
                )
            },
        })
    content_list.append({"type": "text", "text": prompt})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {"role": "user", "content": content_list},
        ],
        "temperature": 0.3,
    }

    try:
        session = _create_session_with_retry()
        r = session.post(url, headers=headers, json=body, timeout=300)
        r.raise_for_status()
        data = r.json()
        choices = data.get("choices", [])
        if choices and len(choices) > 0:
            return choices[0].get("message", {}).get("content", "")
        return "[Vision] 无法解析 Doubao 多模态响应"
    except requests.RequestException as e:
        return f"[Vision] Doubao 多模态 API 调用失败: {e}"


def _call_gemini_vision(prompt: str, images: List[dict]) -> str:
    try:
        import google.generativeai as genai
    except ImportError:
        return "[Vision] google-generativeai 未安装, 请运行: pip install google-generativeai"

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return "[Vision] GEMINI_API_KEY 未设置"

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")

        parts = [VISION_SYSTEM_PROMPT + "\n\n" + prompt]
        for img in images:
            parts.append({
                "mime_type": img.get("mime", "image/jpeg"),
                "data": base64.b64decode(img["base64"]),
            })

        response = model.generate_content(parts)
        return response.text

    except Exception as e:
        return f"[Vision] Gemini 多模态 API 调用失败: {e}"