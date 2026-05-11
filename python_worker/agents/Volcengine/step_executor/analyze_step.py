# -*- coding: utf-8 -*-
# step_executor/analyze_step.py — AlphaPilot OS v3.0
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - analyze_step 必须在 Worker 内执行
#    - 前端、Node API、VSCode 插件都不能分析用户需求
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - analyze 是整个执行链的起点
#    - analyze 必须输出结构化分析（供 plan_step 使用）
#
# 本模块负责：
# 1. 分析用户任务描述
# 2. 提取关键需求点
# 3. 写入上下文（供 plan_step 使用）
# ---------------------------------------------------------

from ..doubao_api import call_doubao
from .prompts import analyze_prompt
from ....worker_config import create_event


def run_analyze_step(step, context, events, api_func=None):
    """
    analyze 步骤（官方 + 智能增强版）
    ---------------------------------------------------------
    输入：
        - 用户任务描述（step["input"]["prompt"]）
    输出：
        - 自然语言分析（结构化）
    """

    # =========================================================
    # ① 获取用户输入（Worker = 真相）
    # =========================================================
    user_input = step["input"].get("prompt", "")

    if not user_input or not user_input.strip():
        fallback = "analyze：未提供任务描述，已自动生成最小分析：用户希望执行一个编程相关任务。"
        step["output"] = {"text": fallback}

        context["intermediate_results"].append({
            "type": "analyze",
            "analysis": fallback
        })

        events.append(create_event("analyze_output", {"analysis": fallback}))
        return

    # =========================================================
    # ② 调用 LLM 生成分析结果（协议 = 宪法）
    # =========================================================
    try:
        llm_call = api_func if api_func else call_doubao
        result = llm_call(analyze_prompt(user_input))

        if not result or not result.strip():
            result = "analyze：LLM 返回空内容，已自动生成最小分析：用户希望执行一个编程任务。"

    except Exception as e:
        result = f"analyze：LLM 调用失败，已自动生成最小分析。错误：{e}"

    # =========================================================
    # ③ 写入输出（供前端展示）
    # =========================================================
    step["output"] = {"text": result}

    # =========================================================
    # ④ 写入上下文（供 plan_step 使用）
    # =========================================================
    context["intermediate_results"].append({
        "type": "analyze",
        "analysis": result
    })

    # =========================================================
    # ⑤ 写入事件流（供 VSCode 实时展示）
    # =========================================================
    events.append(create_event("analyze_output", {"analysis": result}))
