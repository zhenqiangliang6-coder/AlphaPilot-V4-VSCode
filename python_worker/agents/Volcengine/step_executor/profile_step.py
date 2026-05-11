# -*- coding: utf-8 -*-
# step_executor/profile_step.py — AlphaPilot OS v3.0
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - 所有性能分析必须在 Worker 内完成
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - profile_step 可以输出 FileOps（例如 docs/performance.md）
#    - 必须支持多文件协议 v3.0
#
# 本模块负责：
# 1. 执行整个项目（多文件）
# 2. 分析性能瓶颈（LLM + 真实执行）
# 3. 输出性能报告（可选：写入 docs/performance.md）
# ---------------------------------------------------------

from ..doubao_api import call_doubao
from .prompts import profile_prompt
from ....code_executor import run_python_project
from ....worker_config import create_event
from ....file_ops import parse_fileops_v3


def run_profile_step(step, context, events, api_func=None):
    """
    profile 步骤（官方 + 智能增强版）
    ---------------------------------------------------------
    输入：
        - write_step 的多文件协议文本
    输出：
        - 性能分析报告
        - 可选：FileOps（写入 docs/performance.md）
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
        step["output"] = {"text": "profile：未找到 write 步骤生成的代码或文件。"}
        return

    all_code_context = write_outputs[-1]

    # =========================================================
    # ② 执行整个项目（多文件执行）
    # =========================================================
    exec_result = run_python_project(all_code_context)

    exec_summary = (
        f"stdout:\n{exec_result['stdout']}\n\n"
        f"stderr:\n{exec_result['stderr']}\n\n"
        f"error:\n{exec_result['error']}"
    )

    # =========================================================
    # ③ 调用 LLM 进行性能分析（多文件分析）
    # =========================================================
    try:
        llm_call = api_func if api_func else call_doubao
        analysis_text = llm_call(profile_prompt(all_code_context))
    except Exception as e:
        step["output"] = {"text": f"profile：LLM 调用失败：{e}"}
        return

    # =========================================================
    # ④ 生成性能报告（可选：写入 docs/performance.md）
    # =========================================================
    performance_doc = f"""
# 项目性能分析报告

## 执行结果
{exec_summary}

## LLM 性能分析
{analysis_text}
"""

    # 包装成 FileOps（可选）
    performance_protocol = f"# DOC: docs/performance.md\n{performance_doc}"
    performance_file_ops = parse_fileops_v3(performance_protocol)

    # =========================================================
    # ⑤ 写入输出
    # =========================================================
    step["output"] = {
        "text": performance_doc,
        "file_ops": performance_file_ops,
        "exec_summary": exec_summary
    }

    # =========================================================
    # ⑥ 写入上下文（供 refine_step 使用）
    # =========================================================
    context["intermediate_results"].append({
        "type": "profile",
        "text": performance_doc,
        "file_ops": performance_file_ops,
        "exec_summary": exec_summary
    })

    # =========================================================
    # ⑦ 写入事件流（供 VSCode 实时展示）
    # =========================================================
    events.append(create_event("profile_output", {
        "text": performance_doc,
        "file_ops": performance_file_ops,
        "exec_summary": exec_summary
    }))
