# -*- coding: utf-8 -*-
# step_executor/write_step.py — AlphaPilot OS v3.0
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - 所有代码生成必须在 Worker 内部完成
#    - 前端、Node API、VSCode 插件都不能生成文件
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - write_step 必须输出 FileOps（唯一合法的文件操作方式）
#    - FileOps 必须遵守多文件协议 v3.0
#
# 本模块负责：
# 1. 根据 plan 生成多文件代码
# 2. 解析 # FILE / # TEST / # DOC / # META / # DEPENDS
# 3. 生成 FileOps（action/path/type/content）
# ---------------------------------------------------------

from ..doubao_api import call_doubao
from .prompts import write_prompt
from ....worker_config import create_event
from ....file_ops import parse_fileops_v3


def run_write_step(step, context, events, api_func=None):
    """
    write 步骤（官方 + 智能增强版）
    ---------------------------------------------------------
    输入：
        - plan 步骤的规划内容
    输出：
        - LLM 输出的多文件协议文本
        - 解析后的 FileOps（供 Node API 执行）
    """

    # =========================================================
    # ① 获取 plan（Worker = 真相）
    # =========================================================
    plan_outputs = [
        item["plan"]
        for item in context["intermediate_results"]
        if item["type"] == "plan"
    ]

    if not plan_outputs:
        # 智能降级：永不允许 write 步骤断链
        fallback = "# FILE: main.py\nprint('Hello from fallback write_step')"
        step["output"] = {"text": fallback, "file_ops": []}

        context["intermediate_results"].append({
            "type": "write",
            "text": fallback,
            "file_ops": []
        })

        events.append(create_event("write_output", {
            "text": fallback,
            "file_ops": []
        }))
        return

    plan_text = plan_outputs[-1]

    # =========================================================
    # ② 调用 LLM 生成多文件协议（协议 = 宪法）
    # =========================================================
    try:
        llm_call = api_func if api_func else call_doubao
        result = llm_call(write_prompt(plan_text))

        if not result or not result.strip():
            result = "# FILE: main.py\nprint('LLM returned empty result')"

    except Exception as e:
        result = f"# FILE: main.py\nprint('LLM 调用失败: {e}')"

    # =========================================================
    # ③ 解析多文件协议 → FileOps（核心）
    # =========================================================
    file_ops = parse_fileops_v3(result)

    # =========================================================
    # ④ 写入输出（供 refine/test 使用）
    # =========================================================
    step["output"] = {
        "text": result,
        "file_ops": file_ops
    }

    # =========================================================
    # ⑤ 写入上下文（供 refine/test 使用）
    # =========================================================
    context["intermediate_results"].append({
        "type": "write",
        "text": result,
        "file_ops": file_ops
    })

    # =========================================================
    # ⑥ 写入事件流（供 VSCode 实时展示）
    # =========================================================
    events.append(create_event("write_output", {
        "text": result,
        "file_ops": file_ops
    }))
