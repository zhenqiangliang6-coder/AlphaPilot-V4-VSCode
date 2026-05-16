# -*- coding: utf-8 -*-
# step_executor/refine_step.py
# ---------------------------------------------------------
# refine 步骤：执行代码 + 优化代码
# - ⭐ v3.0：支持自定义 api_func（用于流式输出）
# ---------------------------------------------------------

from .qwen_api import call_qwen
from .utils import extract_code, FAKE_ENVIRONMENT
from .prompts import optimize_prompt
from code_executor import run_python
from worker_config import create_event


def run_refine_step(step, context, events):
    """
    refine 步骤：
    - 执行 write 步骤生成的代码
    - 根据执行结果优化代码
    - ⭐ v3.0：支持通过 context['_custom_api_func'] 传入自定义 API 函数
    """

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

    # 3) ⭐ v3.0：选择 API 调用函数
    api_func = context.get("_custom_api_func", call_qwen)

    # 4) 调用 LLM 优化代码
    try:
        optimized_text = api_func(optimize_prompt(code, exec_summary))
    except Exception as e:
        step["output"] = {"text": f"refine：LLM 调用失败：{e}"}
        return

    optimized_code = extract_code(optimized_text)

    # 5) 写入输出
    step["output"] = {
        "text": optimized_text,
        "optimized_code": optimized_code,
        "exec_summary": exec_summary
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
