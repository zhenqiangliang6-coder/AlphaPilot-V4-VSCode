# -*- coding: utf-8 -*-
# step_executor/analyze_step.py
# ---------------------------------------------------------
# analyze 步骤：分析用户需求，提取关键点
# ---------------------------------------------------------

from step_executor.qwen_api import call_qwen
from step_executor.prompts import analyze_prompt
from worker_config import create_event


def run_analyze_step(step, context, events):
    """
    analyze 步骤：
    - 输入：用户任务描述
    - 输出：需求分析（自然语言）
    """

    # 1) 获取用户输入
    user_input = step["input"].get("prompt", "")

    if not user_input:
        step["output"] = {"text": "analyze：未提供任务描述。"}
        return

    # 2) 调用 LLM 生成分析结果
    try:
        result = call_qwen(analyze_prompt(user_input))
    except Exception as e:
        step["output"] = {"text": f"analyze：LLM 调用失败：{e}"}
        return

    # 3) 写入输出
    step["output"] = {"text": result}

    # 4) 写入上下文（供 plan_step 使用）
    context["intermediate_results"].append({
        "type": "analyze",
        "analysis": result
    })

    # 5) 写入事件流（供 VSCode 实时展示）
    events.append(create_event("analyze_output", {
        "analysis": result
    }))
