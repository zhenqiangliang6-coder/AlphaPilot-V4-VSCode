# -*- coding: utf-8 -*-
# step_executor/fix_step.py
# ---------------------------------------------------------
# Local LLM Worker v3.0 — fix 步骤（v3.0 流式输出版本）
# - ⭐ v3.0：支持流式输出（task_id 参数）
# - ⭐ 与 Qwen Worker v2 完全对齐
# ---------------------------------------------------------

from .utils import extract_code, FAKE_ENVIRONMENT
from .prompts import fix_prompt
from code_executor import run_python
from worker_config import create_event, stream_chunk, stream_start, stream_end
from ..local_api import call_local_llm


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
    fix 步骤（v3.0）：
    - 输入：write 步骤的代码和执行错误
    - 输出：修复后的代码
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
            stream_start(task_id, "🔧 正在修复代码错误...", phase="fix")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")
    
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
        return

    # ⭐ v3.0：选择 API 调用函数
    if llm_client is not None:
        api_func = llm_client.call
    else:
        api_func = context.get("_custom_api_func", call_local_llm)

    # ⭐ 获取测试代码
    error_info, test_code = _get_test_context(context)

    # 调用 LLM 修复代码（⭐ 支持流式输出）
    fixed_text = ""
    llm_success = False

    try:
        prompt = fix_prompt(code, exec_result["error"], test_code)

        if task_id:
            # ⭐ 流式输出模式
            stream_chunk(task_id, "分析错误并修复...\n", phase="fix", channel="reasoning")
            
            # 使用注入的 LLM 客户端或默认实现
            fixed_text = api_func(prompt)
            stream_chunk(task_id, fixed_text, phase="fix", channel="content")
        else:
            # 同步调用模式
            fixed_text = api_func(prompt)

        if not fixed_text:
            raise ValueError("LLM 返回空字符串")

        llm_success = True

    except Exception as e:
        err = f"# LLM 调用失败: {e}"
        fixed_text = err
        if task_id:
            stream_chunk(task_id, err, phase="fix", channel="reasoning")

    fixed_code = extract_code(fixed_text)

    # ⭐ 依赖注入：使用注入的代码执行器，或默认使用真实实现
    if code_executor is not None:
        verify = code_executor.execute(FAKE_ENVIRONMENT + "\n\n" + fixed_code)
    else:
        verify = run_python(FAKE_ENVIRONMENT + "\n\n" + fixed_code)

    step["output"] = {
        "text": fixed_text
        + "\n\n---\n\n验证结果：\n"
        + f"stdout:\n{verify['stdout']}\n\nstderr:\n{verify['stderr']}\n\nerror:\n{verify['error']}",
        "llm_success": llm_success
    }

    # ===== 7. 流式输出结束 =====
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
