# -*- coding: utf-8 -*-
# step_executor/write_step.py
# ---------------------------------------------------------
# write 步骤：根据 plan 生成代码（Gemini 版 — 流式输出 + 人格配置）
# ---------------------------------------------------------

from ..gemini_api import call_gemini, call_gemini_stream, call_gemini_with_persona
from .utils import extract_code
from .prompts import write_prompt
from ....worker_config import create_event, stream_chunk, stream_start, stream_end


def run_write_step(step, context, events, task_id=None):
    """
    write 步骤（Gemini 版）：
    - 输入：plan 步骤的规划
    - 输出：生成的 Python 代码
    """

    # ===== 启动流式输出 =====
    if task_id:
        try:
            stream_start(task_id, "✍️ Gemini 正在生成代码...", phase="write")
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

    # 1) 获取 plan 步骤的输出（若无 plan 则回退到 analyze 输出 + 用户请求）
    meta = context.get("meta", {})
    user_request = meta.get("user_request", "")

    plan_outputs = [
        item["plan"]
        for item in context["intermediate_results"]
        if item["type"] == "plan"
    ]

    if not plan_outputs:
        analyze_outputs = [
            item.get("analysis", "") or item.get("text", "")
            for item in context.get("intermediate_results", [])
            if item.get("type") == "analyze"
        ]
        if analyze_outputs:
            plan_text = f"# 任务分析\n{analyze_outputs[-1]}\n\n# 用户原始请求\n{user_request}"
            print(f"[INFO] write_step 未找到 plan，回退使用 analyze 输出 + 用户请求")
        else:
            plan_text = user_request or "请根据上下文生成内容"
            print(f"[INFO] write_step 未找到 plan 和 analyze，回退使用用户请求")
    else:
        plan_text = plan_outputs[-1]

    # 2) 调用 LLM 生成代码（流式 + 人格）
    result = ""
    try:
        prompt = write_prompt(plan_text)
        
        if task_id:
            if persona_config:
                for chunk in call_gemini_with_persona(prompt, persona_config, use_stream=True):
                    result += chunk
                    stream_chunk(task_id, chunk, phase="write", channel="code")
            else:
                for chunk in call_gemini_stream(prompt):
                    result += chunk
                    stream_chunk(task_id, chunk, phase="write", channel="code")
        else:
            if persona_config:
                result = call_gemini_with_persona(prompt, persona_config, use_stream=False)
            else:
                result = call_gemini(prompt)
    except Exception as e:
        result = f"write：LLM 调用失败：{e}"

    # 3) 提取代码块
    code = extract_code(result)

    # 4) 写入输出
    step["output"] = {
        "text": result,
        "code": code
    }

    # 5) 写入上下文（供 refine/test/fix/profile/doc 使用）
    context["intermediate_results"].append({
        "type": "write",
        "text": result,
        "code": code
    })

    # 6) 写入事件流（供 VSCode 实时展示）
    events.append(create_event("write_output", {
        "text": result,
        "code": code
    }))

    # ⭐ 结束流式输出
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")