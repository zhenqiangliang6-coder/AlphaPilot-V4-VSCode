# -*- coding: utf-8 -*-
# step_executor/refine_step.py — AlphaPilot OS v3.0
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - 所有代码执行、错误分析、优化都必须在 Worker 内完成
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - refine_step 必须输出 FileOps（唯一合法的文件操作方式）
#    - 必须支持多文件协议 v3.0
#
# 本模块负责：
# 1. 执行 write_step 生成的代码（多文件）
# 2. 根据执行结果优化整个项目
# 3. 输出新的 FileOps（覆盖旧文件）
# ---------------------------------------------------------

from ..doubao_api import call_doubao
from .prompts import optimize_prompt  # ⭐ 修复：使用正确的函数名
from ....code_executor import run_python_project
from ....worker_config import create_event
from ....file_ops import parse_fileops_v3


def run_refine_step(step, context, events, api_func=None):
    """
    refine 步骤（官方 + 智能增强版）
    ---------------------------------------------------------
    输入：
        - write_step 的多文件协议文本
    输出：
        - 优化后的多文件协议
        - 新的 FileOps（覆盖旧文件）
    """

    # =========================================================
    # ① 获取 write_step 的多文件协议文本
    # =========================================================
    write_outputs = [
        item["text"]
        for item in context["intermediate_results"]
        if item["type"] == "write"
    ]

    if not write_outputs:
        step["output"] = {"text": "refine：未找到 write 步骤生成的代码或文件。"}
        return

    all_code_context = write_outputs[-1]

    # =========================================================
    # ② 执行整个项目（多文件执行）
    # =========================================================
    try:
        exec_result = run_python_project(all_code_context)
    except Exception as e:
        exec_summary = f"refine：代码执行异常：{e}"
        step["output"] = {"text": exec_summary}
        return

    exec_summary = (
        f"stdout:\n{exec_result['stdout']}\n\n"
        f"stderr:\n{exec_result['stderr']}\n\n"
        f"error:\n{exec_result['error']}"
    )

    # =========================================================
    # ③ 调用 LLM 优化整个项目（多文件优化）
    # =========================================================
    try:
        llm_call = api_func if api_func else call_doubao
        optimized_text = llm_call(
            optimize_prompt_v28(all_code_context, exec_summary)
        )
    except Exception as e:
        step["output"] = {"text": f"refine：LLM 调用失败：{e}"}
        return

    # =========================================================
    # ④ 解析优化后的多文件协议 → FileOps
    # =========================================================
    optimized_file_ops = parse_fileops_v3(optimized_text)

    # =========================================================
    # ⑤ 写入输出
    # =========================================================
    step["output"] = {
        "text": optimized_text,
        "file_ops": optimized_file_ops,
        "exec_summary": exec_summary
    }

    # =========================================================
    # ⑥ 写入上下文（供后续步骤使用）
    # =========================================================
    context["intermediate_results"].append({
        "type": "refine",
        "text": optimized_text,
        "file_ops": optimized_file_ops,
        "exec_summary": exec_summary
    })

    # =========================================================
    # ⑦ 写入事件流（供 VSCode 实时展示）
    # =========================================================
    events.append(create_event("refine_output", {
        "text": optimized_text,
        "file_ops": optimized_file_ops,
        "exec_summary": exec_summary
    }))
