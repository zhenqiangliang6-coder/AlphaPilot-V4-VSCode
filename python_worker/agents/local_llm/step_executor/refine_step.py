# -*- coding: utf-8 -*-
# step_executor/refine_step.py
# ---------------------------------------------------------
# Local LLM Worker v3.0 — refine 步骤（v3.0 流式输出版本）
# - ⭐ v3.0：支持流式输出（task_id 参数）
# - ⭐ 与 Qwen Worker v2 完全对齐
# ---------------------------------------------------------

from .qwen_api import call_qwen
from .utils import extract_code, FAKE_ENVIRONMENT
from .prompts import optimize_prompt
from code_executor import run_python
from worker_config import create_event, stream_chunk, stream_start, stream_end


def run_refine_step(step, context, events, task_id=None):
    """
    refine 步骤（v3.0）：
    - 执行 write 步骤生成的代码
    - 根据执行结果优化代码
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
            stream_start(task_id, "⚙️ 正在执行并优化代码...", phase="refine")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

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
    exec_result = None
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

    # 3) ⭐ v3.0：选择 API 调用函数
    api_func = context.get("_custom_api_func", call_qwen)

    # 4) 调用 LLM 优化代码（⭐ 支持流式输出）
    optimized_text = ""
    llm_success = False

    try:
        prompt = optimize_prompt(code, exec_summary)

        if task_id:
            # ⭐ 流式输出模式
            stream_chunk(task_id, "开始优化代码...\n", phase="refine", channel="reasoning")
            
            # 注意：Local LLM 的 call_qwen 目前不支持真正的流式，这里先同步调用
            optimized_text = api_func(prompt)
            stream_chunk(task_id, optimized_text, phase="refine", channel="content")
        else:
            # 同步调用模式
            optimized_text = api_func(prompt)

        if not optimized_text:
            raise ValueError("LLM 返回空字符串")

        llm_success = True

    except Exception as e:
        err = f"# LLM 调用失败: {e}"
        optimized_text = err
        if task_id:
            stream_chunk(task_id, err, phase="refine", channel="reasoning")

    optimized_code = extract_code(optimized_text)

    # 5) 写入输出
    step["output"] = {
        "text": optimized_text,
        "optimized_code": optimized_code,
        "exec_summary": exec_summary,
        "llm_success": llm_success
    }

    # 6) 写入上下文（供后续步骤使用）
    context["intermediate_results"].append({
        "type": "refine",
        "original_code": code,
        "optimized_code": optimized_code,
        "exec_summary": exec_summary
    })

    # 7) 写入事件流（供 VSCode 实时展示）
    events.append(create_event("refine_output", {
        "original_code": code,
        "optimized_code": optimized_code,
        "exec_summary": exec_summary
    }))

    # ===== 8. 流式输出结束 =====
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
