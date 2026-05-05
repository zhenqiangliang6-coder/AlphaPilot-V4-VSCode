# -*- coding: utf-8 -*-
# step_executor/plan_step.py
# ---------------------------------------------------------
# plan 步骤：生成代码结构规划
# ---------------------------------------------------------

from ..doubao_api import call_doubao
from .prompts import plan_prompt
from ....worker_config import create_event


def run_plan_step(step, context, events, api_func=None):
    """
    plan 步骤：
    - 输入：analyze 步骤的分析结果
    - 输出：代码结构规划（自然语言 + 伪代码）
    
    参数:
        api_func: 可选的自定义 API 函数，如果不传则使用默认的 call_doubao
    """

    # 1) 获取 analyze 步骤的输出
    analyze_outputs = [
        item["analysis"]
        for item in context["intermediate_results"]
        if item["type"] == "analyze"
    ]

    if not analyze_outputs:
        step["output"] = {"text": "plan：未找到 analyze 步骤的分析结果。"}
        return

    analysis = analyze_outputs[-1]

    # 2) 调用 LLM 生成规划
    try:
        llm_call = api_func if api_func else call_doubao
        result = llm_call(plan_prompt(analysis))
    except Exception as e:
        step["output"] = {"text": f"plan：LLM 调用失败：{e}"}
        return

    # 3) 写入输出
    step["output"] = {"text": result}

    # 4) 写入上下文（供 write_step 使用）
    context["intermediate_results"].append({
        "type": "plan",
        "plan": result
    })

    # 5) 写入事件流（供 VSCode 实时展示）
    events.append(create_event("plan_output", {
        "plan": result
    }))
