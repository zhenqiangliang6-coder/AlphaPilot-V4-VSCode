# -*- coding: utf-8 -*-
# step_executor/fix_step.py — AlphaPilot OS v3.0
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - 所有修复逻辑必须在 Worker 内完成
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - fix_step 必须输出 FileOps（唯一合法的文件操作方式）
#    - 必须支持多文件协议 v3.0
#
# 本模块负责：
# 1. 执行 write_step 生成的整个项目
# 2. 根据错误信息修复整个项目（多文件）
# 3. 输出新的 FileOps（覆盖旧文件）
# ---------------------------------------------------------

from ..doubao_api import call_doubao
from .prompts import fix_prompt
from ....code_executor import run_python_project
from ....worker_config import create_event
from ....file_ops import parse_fileops_v3


def run_fix_step(step, context, events, api_func=None):
    """
    fix 步骤（官方 + 智能增强版）
    ---------------------------------------------------------
    输入：
        - write_step 的多文件协议文本
    输出：
        - 修复后的多文件协议
        - FileOps（覆盖旧文件）
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
        step["output"] = {"text": "fix：未找到 write 步骤生成的代码或文件。"}
        return

    all_code_context = write_outputs[-1]

    # =========================================================
    # ② 执行整个项目（多文件执行）
    # =========================================================
    exec_result = run_python_project(all_code_context)

    if not exec_result["error"]:
        step["output"] = {"text": "fix：代码执行成功，无需修复。"}
        return

    error_message = exec_result["error"]

    # =========================================================
    # ③ 调用 LLM 修复整个项目（多文件修复）
    # =========================================================
    try:
        llm_call = api_func if api_func else call_doubao
        fixed_text = llm_call(fix_prompt(all_code_context, error_message))
    except Exception as e:
        step["output"] = {"text": f"fix：LLM 调用失败：{e}"}
        return

    # =========================================================
    # ④ 解析修复后的多文件协议 → FileOps
    # =========================================================
    fixed_file_ops = parse_fileops_v3(fixed_text)

    # =========================================================
    # ⑤ 写入输出
    # =========================================================
    step["output"] = {
        "text": fixed_text,
        "file_ops": fixed_file_ops,
        "error_before_fix": error_message
    }

    # =========================================================
    # ⑥ 写入上下文（供 refine_step 使用）
    # =========================================================
    context["intermediate_results"].append({
        "type": "fix",
        "text": fixed_text,
        "file_ops": fixed_file_ops,
        "error_before_fix": error_message
    })

    # =========================================================
    # ⑦ 写入事件流（供 VSCode 实时展示）
    # =========================================================
    events.append(create_event("fix_output", {
        "text": fixed_text,
        "file_ops": fixed_file_ops,
        "error_before_fix": error_message
    }))
