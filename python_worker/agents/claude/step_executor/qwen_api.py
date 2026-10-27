# -*- coding: utf-8 -*-
# step_executor/qwen_api.py
# ---------------------------------------------------------
# Qwen API 调用封装
# - 统一入口：agents.qwen.qwen_api（运行时探测 + 自动降级）
# ---------------------------------------------------------

from agents.qwen.qwen_api import call_qwen

__all__ = ["call_qwen"]