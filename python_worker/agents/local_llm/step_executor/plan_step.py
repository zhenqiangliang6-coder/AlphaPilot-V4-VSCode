# -*- coding: utf-8 -*-
# step_executor/plan_step.py
# ---------------------------------------------------------
# Local LLM Worker v3.0 — plan 步骤（v3.0 流式输出版本）
# - ⭐ v3.0：支持流式输出（task_id 参数）
# - ⭐ 与 Qwen Worker v2 完全对齐
# ---------------------------------------------------------

from ..local_api import call_local_llm
from .prompts import plan_prompt
from worker_config import create_event, stream_chunk, stream_start, stream_end


def run_plan_step(step, context, events, task_id=None):
    """
    plan 步骤（v3.0）：
    - 输入：analyze 步骤的分析结果
    - 输出：代码结构规划（自然语言 + 伪代码）
    - ⭐ v3.0：支持流式输出（通过 task_id 参数）
    
    参数:
        step: 步骤定义
        context: 上下文对象
        events: 事件列表
        task_id: 任务 ID（可选，用于流式输出）
    """

    # ===== 0. 流式输出开始 =====
    if task_id:
        try:
            stream_start(task_id, "📋 正在制定执行计划...", phase="plan")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

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
    api_func = context.get("_custom_api_func", call_local_llm)

    # 3) 调用 LLM 生成规划（⭐ 支持流式输出）
    result = ""
    llm_success = False

    try:
        prompt = plan_prompt(analysis)

        if task_id:
            # ⭐ 流式输出模式
            stream_chunk(task_id, "开始制定计划...\n", phase="plan", channel="reasoning")
            
            # 注意：Local LLM 的 call_qwen 目前不支持真正的流式，这里先同步调用
            result = api_func(prompt)
            stream_chunk(task_id, result, phase="plan", channel="content")
        else:
            # 同步调用模式
            result = api_func(prompt)

        if not result:
            raise ValueError("LLM 返回空字符串")

        llm_success = True

    except Exception as e:
        err = f"# LLM 调用失败: {e}"
        result = err
        if task_id:
            stream_chunk(task_id, err, phase="plan", channel="reasoning")

    # 4) 写入输出
    step["output"] = {
        "text": result,
        "llm_success": llm_success
    }

    # 5) 写入上下文（供 write_step 使用）
    context["intermediate_results"].append({
        "type": "plan",
        "plan": result
    })

    # 6) 写入事件流（供 VSCode 实时展示）
    events.append(create_event("plan_output", {
        "plan": result
    }))

    # ===== 7. 流式输出结束 =====
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
