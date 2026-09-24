# -*- coding: utf-8 -*-
# step_executor/refine_step.py
# ---------------------------------------------------------
# refine 步骤：执行代码 + 优化代码（Gemini 版 — 流式输出 + 人格配置）
# ---------------------------------------------------------

from ..gemini_api import call_gemini, call_gemini_stream, call_gemini_with_persona
from .utils import extract_code, FAKE_ENVIRONMENT
from .prompts import optimize_prompt
from ....code_executor import run_python
from ....worker_config import create_event, stream_chunk, stream_start, stream_end


def run_refine_step(step, context, events, task_id=None):
    """
    refine 步骤（Gemini 版）：
    - 执行 write 步骤生成的代码
    - 根据执行结果优化代码
    """

    # ===== 启动流式输出 =====
    if task_id:
        try:
            stream_start(task_id, "🔧 Gemini 正在优化代码...", phase="refine")
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

    # 1) 获取 write 步骤的代码
    write_outputs = [
        item["code"]
        for item in context["intermediate_results"]
        if item["type"] == "write"
    ]

    if not write_outputs:
        step["output"] = {"text": "refine：未找到 write 步骤生成的代码。"}
        return

    code = write_outputs[-1]

    # 2) 执行代码（使用 mock 环境）
    try:
        exec_result = run_python(FAKE_ENVIRONMENT + "\n\n" + code)
    except Exception as e:
        step["output"] = {"text": f"refine：代码执行失败：{e}"}
        return

    exec_summary = (
        f"stdout:\n{exec_result['stdout']}\n\n"
        f"stderr:\n{exec_result['stderr']}\n\n"
        f"error:\n{exec_result['error']}"
    )

    # 3) 调用 LLM 优化代码（流式 + 人格）
    optimized_text = ""
    try:
        prompt = optimize_prompt(code, exec_summary)
        
        if task_id:
            if persona_config:
                for chunk in call_gemini_with_persona(prompt, persona_config, use_stream=True):
                    optimized_text += chunk
                    stream_chunk(task_id, chunk, phase="refine", channel="code")
            else:
                for chunk in call_gemini_stream(prompt):
                    optimized_text += chunk
                    stream_chunk(task_id, chunk, phase="refine", channel="code")
        else:
            if persona_config:
                optimized_text = call_gemini_with_persona(prompt, persona_config, use_stream=False)
            else:
                optimized_text = call_gemini(prompt)
    except Exception as e:
        optimized_text = f"refine：LLM 调用失败：{e}"

    optimized_code = extract_code(optimized_text)

    # 4) 写入输出
    step["output"] = {
        "text": optimized_text,
        "optimized_code": optimized_code,
        "exec_summary": exec_summary
    }

    # 5) 写入上下文（供后续步骤使用）
    context["intermediate_results"].append({
        "type": "refine",
        "original_code": code,
        "optimized_code": optimized_code,
        "exec_summary": exec_summary
    })

    # 6) 写入事件流（供 VSCode 实时展示）
    events.append(create_event("refine_output", {
        "original_code": code,
        "optimized_code": optimized_code,
        "exec_summary": exec_summary
    }))

    # ⭐ 结束流式输出
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
