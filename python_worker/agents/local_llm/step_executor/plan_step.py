# -*- coding: utf-8 -*-
# step_executor/plan_step.py
# ---------------------------------------------------------
# plan 步骤：生成代码结构规划
# - ⭐ v3.0：支持自定义 api_func（用于流式输出）
# ---------------------------------------------------------

from .qwen_api import call_qwen
from .prompts import plan_prompt
from worker_config import create_event


def run_plan_step(step, context, events):
    """
    plan 步骤：
    - 输入：analyze 步骤的分析结果
    - 输出：代码结构规划（自然语言 + 伪代码）
    - ⭐ v3.0：支持通过 context['_custom_api_func'] 传入自定义 API 函数
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

    # 2) ⭐ v3.0：选择 API 调用函数
    api_func = context.get("_custom_api_func", call_qwen)

    # 3) 调用 LLM 生成规划
    try:
        result = api_func(plan_prompt(analysis))
    except Exception as e:
        step["output"] = {"text": f"plan：LLM 调用失败：{e}"}
        return

    # 4) 写入输出
    step["output"] = {"text": result}

    # 5) 写入上下文（供 write_step 使用）
    context["intermediate_results"].append({
        "type": "plan",
        "plan": result
    })

    # 6) 写入事件流（供 VSCode 实时展示）
    events.append(create_event("plan_output", {
        "plan": result
    }))
