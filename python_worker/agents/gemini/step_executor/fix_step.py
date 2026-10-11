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


def _get_test_context(context):
    """
    从 context 中提取测试代码和错误信息
    
    参数:
        context: 执行上下文
    
    返回:
        (error_info, test_code): 错误信息和测试代码
    """
    error_info = ""
    test_code = ""
    
    # 从 intermediate_results 中提取
    for item in context.get("intermediate_results", []):
        if item.get("type") == "test":
            # 提取错误信息
            error = item.get("error", "")
            if error:
                error_info = error
            # 提取测试代码
            tc = item.get("test_code", "")
            if tc:
                test_code = tc
            break
    
    # 如果没有找到测试代码，尝试从其他来源提取
    if not error_info:
        error_info = context.get("last_error", "")
    
    return error_info, test_code


def run_fix_step(
    step, 
    context, 
    events, 
    task_id=None,
    llm_client=None,  # ⭐ 依赖注入：LLM 客户端
    code_executor=None  # ⭐ 依赖注入：代码执行器
):
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
    
    # ⭐ 依赖注入：使用注入的代码执行器，或默认使用真实实现
    if code_executor is not None:
        exec_result = code_executor.execute(FAKE_ENVIRONMENT + "\n\n" + code)
    else:
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
    # ⭐ 获取测试代码
    error_info, test_code = _get_test_context(context)
    
    fixed_text = ""
    try:
        prompt = fix_prompt(code, exec_result["error"], test_code)
        
        # ⭐ 依赖注入：使用注入的 LLM 客户端，或默认使用真实实现
        if llm_client is not None:
            # 使用注入的依赖
            if task_id and hasattr(llm_client, 'call_stream'):
                for chunk in llm_client.call_stream(prompt):
                    fixed_text += chunk
                    stream_chunk(task_id, chunk, phase="fix", channel="code")
            else:
                fixed_text = llm_client.call(prompt)
        else:
            # 使用默认实现
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

    # ⭐ 依赖注入：使用注入的代码执行器，或默认使用真实实现
    if code_executor is not None:
        verify = code_executor.execute(FAKE_ENVIRONMENT + "\n\n" + fixed_code)
    else:
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
