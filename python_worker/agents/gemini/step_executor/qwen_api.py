# -*- coding: utf-8 -*-
# step_executor/qwen_api.py
# ---------------------------------------------------------
# Gemini API 桥接层（供 step_executor 内部调用）
# 将 gemini_api.py 的 call_gemini 暴露为 call_qwen 以保持向后兼容
# ⭐ 所有 LLM 调用统一走 Google Gemini 原生接口
# ---------------------------------------------------------

import sys
import os

# 添加父目录到路径，以便从上级目录导入 gemini_api
# 假设 gemini_api.py 位于 step_executor 的父目录中
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    from gemini_api import call_gemini
except ImportError:
    # 如果 gemini_api 在当前目录或其他位置，尝试直接导入
    try:
        from ..gemini_api import call_gemini
    except ImportError:
        raise ImportError("无法找到 gemini_api 模块，请确保 gemini_api.py 存在于正确的目录中。")


def call_qwen(prompt: str) -> str:
    """
    向后兼容接口：内部调用 Google Gemini API
    
    参数:
        prompt: 提示词字符串
    
    返回:
        str: LLM 生成的文本响应
    """
    return call_gemini(prompt)
