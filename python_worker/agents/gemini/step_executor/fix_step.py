# -*- coding: utf-8 -*-
# step_executor/fix_step.py
# ---------------------------------------------------------
# fix 步骤：mock-aware 修复（Gemini 版 — 流式输出 + 人格配置）
# ---------------------------------------------------------

from .utils import extract_code, FAKE_ENVIRONMENT
from .prompts import fix_prompt
from ....code_executor import run_python
from ..gemini_api import call_gemini, call_gemini_stream, call_gemini_with_persona
from ....worker_config import create_event, stream_chunk, stream_start, stream_end


def run_fix_step(step, context, events, task_id=None):
    """
    fix 步骤（Gemini 版）：
    - 执行 write 步骤的代码
    - 如果有错误，让 LLM 修复
    - 验证修复结果
    """

    # ===== 启动流式输出 =====
    if task_id:
        try:
            stream_start(task_id, "🔨 Gemini 正在修复代码...", phase="fix")
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

    write_outputs = [i["text"] for i in context["intermediate_results"] if i["type"] == "write"]
    if not write_outputs:
        step["output"] = {"text": "fix：未找到 write 步骤的代码。"}
        return

    code = extract_code(write_outputs[-1])
    exec_result = run_python(FAKE_ENVIRONMENT + "\n\n" + code)

    if not exec_result["error"]:
        step["output"] = {"text": "fix：代码执行成功，无需修复。"}
        if task_id:
            try:
                stream_end(task_id)
            except Exception as e:
                print(f"[WARN] stream_end 失败: {e}")
        return

    # 调用 Gemini 修复代码（流式 + 人格）
    fixed_text = ""
    try:
        prompt = fix_prompt(code, exec_result["error"])
        
        if task_id:
            if persona_config:
                for chunk in call_gemini_with_persona(prompt, persona_config, use_stream=True):
                    fixed_text += chunk
                    stream_chunk(task_id, chunk, phase="fix", channel="code")
            else:
                for chunk in call_gemini_stream(prompt):
                    fixed_text += chunk
                    stream_chunk(task_id, chunk, phase="fix", channel="code")
        else:
            fixed_text = call_gemini(prompt)
    except Exception as e:
        fixed_text = f"fix：LLM 调用失败：{e}"

    fixed_code = extract_code(fixed_text)

    verify = run_python(FAKE_ENVIRONMENT + "\n\n" + fixed_code)

    step["output"] = {
        "text": fixed_text
        + "\n\n---\n\n验证结果：\n"
        + f"stdout:\n{verify['stdout']}\n\nstderr:\n{verify['stderr']}\n\nerror:\n{verify['error']}"
    }

    # ⭐ 结束流式输出
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
