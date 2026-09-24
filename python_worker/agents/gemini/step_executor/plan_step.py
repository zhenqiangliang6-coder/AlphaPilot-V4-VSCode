# -*- coding: utf-8 -*-
# step_executor/plan_step.py
# ---------------------------------------------------------
# plan 步骤：生成代码结构规划（Gemini 版 — 流式输出 + 人格配置）
# ---------------------------------------------------------

from ..gemini_api import call_gemini, call_gemini_stream, call_gemini_with_persona
from .prompts import plan_prompt
from ....worker_config import create_event, stream_chunk, stream_start, stream_end


def run_plan_step(step, context, events, task_id=None):
    """
    plan 步骤（Gemini 版）：
    - 输入：analyze 步骤的分析结果
    - 输出：代码结构规划（自然语言 + 伪代码）
    """

    # ===== 启动流式输出 =====
    if task_id:
        try:
            stream_start(task_id, "📋 Gemini 正在制定执行计划...", phase="plan")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # ===== 获取人格配置 =====
    persona_config = None
    try:
        meta = context.get("meta", {})
        persona_type = meta.get("persona", "engineer")
        from ..personas import get_persona_config
        persona_config = get_persona_config(persona_type)
    except Exception as e:
        print(f"[WARN] 获取人格配置失败: {e}")

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

    # 2) 调用 LLM 生成规划（流式 + 人格）
    result = ""
    try:
        prompt = plan_prompt(analysis)
        
        if task_id:
            if persona_config:
                for chunk in call_gemini_with_persona(prompt, persona_config, use_stream=True):
                    result += chunk
                    stream_chunk(task_id, chunk, phase="plan", channel="reasoning")
            else:
                for chunk in call_gemini_stream(prompt):
                    result += chunk
                    stream_chunk(task_id, chunk, phase="plan", channel="reasoning")
        else:
            if persona_config:
                result = call_gemini_with_persona(prompt, persona_config, use_stream=False)
            else:
                result = call_gemini(prompt)
    except Exception as e:
        result = f"plan：LLM 调用失败：{e}"

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

    # ⭐ 结束流式输出
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
