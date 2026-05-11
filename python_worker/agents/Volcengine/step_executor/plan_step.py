# -*- coding: utf-8 -*-
# step_executor/plan_step.py — AlphaPilot OS v3.0
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - 所有规划逻辑必须在 Worker 内部执行
#    - 前端、Node API、VSCode 插件都不能生成或修改 plan
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - plan 是 write 的唯一输入来源
#    - write 必须依赖 plan，不允许跳过
#    - plan 必须结构化、可预测、可验证
#
# 本模块负责：
# 1. 根据 analyze 结果生成代码结构规划
# 2. 保证 write_step 永远能找到 plan（智能增强）
# 3. 将 plan 写入上下文和事件流
# ---------------------------------------------------------

from ..doubao_api import call_doubao
from .prompts import plan_prompt
from ....worker_config import create_event


def run_plan_step(step, context, events, api_func=None):
    """
    plan 步骤（官方 + 智能增强版）
    ---------------------------------------------------------
    输入：
        - analyze 步骤的分析结果（必须存在）
    输出：
        - 代码结构规划（自然语言 + 伪代码）
    
    智能增强：
        - 如果 analyze 输出为空，自动降级为“最小可用规划”
        - 保证 write_step 永远不会出现 “未找到 plan” 的情况
    """

    # =========================================================
    # ① 获取 analyze 步骤输出（Worker = 真相）
    # =========================================================
    analyze_outputs = [
        item["analysis"]
        for item in context["intermediate_results"]
        if item["type"] == "analyze"
    ]

    if not analyze_outputs:
        # 智能降级：生成最小可用 plan，避免 write 步骤断链
        fallback_plan = "系统未找到 analyze 输出，已自动生成最小规划：创建一个 main.py 文件并实现核心逻辑。"
        step["output"] = {"text": fallback_plan}

        context["intermediate_results"].append({
            "type": "plan",
            "plan": fallback_plan
        })

        events.append(create_event("plan_output", {"plan": fallback_plan}))
        return

    analysis = analyze_outputs[-1]

    # =========================================================
    # ② 调用 LLM 生成规划（协议 = 宪法）
    # =========================================================
    try:
        llm_call = api_func if api_func else call_doubao
        result = llm_call(plan_prompt(analysis))

        # 如果 LLM 返回空内容，自动生成 fallback 规划
        if not result or not result.strip():
            result = "LLM 未返回规划内容，已自动生成最小规划：创建 main.py 并实现核心逻辑。"

    except Exception as e:
        # 智能降级：LLM 调用失败也不能断链
        result = f"plan 步骤 LLM 调用失败，已自动生成最小规划：创建 main.py。错误信息：{e}"

    # =========================================================
    # ③ 写入输出（供前端展示）
    # =========================================================
    step["output"] = {"text": result}

    # =========================================================
    # ④ 写入上下文（供 write_step 使用）
    # =========================================================
    context["intermediate_results"].append({
        "type": "plan",
        "plan": result
    })

    # =========================================================
    # ⑤ 写入事件流（供 VSCode 实时展示）
    # =========================================================
    events.append(create_event("plan_output", {"plan": result}))
