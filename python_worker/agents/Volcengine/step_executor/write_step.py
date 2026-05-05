# -*- coding: utf-8 -*-
# step_executor/write_step.py
# ---------------------------------------------------------
# write 步骤：根据 plan 生成代码
# ---------------------------------------------------------

from ..doubao_api import call_doubao
from .utils import extract_code
from .prompts import write_prompt
from ....worker_config import create_event


def run_write_step(step, context, events, api_func=None):
    """
    write 步骤：
    - 输入：plan 步骤的规划
    - 输出：生成的 Python 代码
    
    参数:
        api_func: 可选的自定义 API 函数，如果不传则使用默认的 call_doubao
    """

    # 1) 获取 plan 步骤的输出
    plan_outputs = [
        item["plan"]
        for item in context["intermediate_results"]
        if item["type"] == "plan"
    ]

    if not plan_outputs:
        step["output"] = {"text": "write：未找到 plan 步骤的规划内容。"}
        return

    plan_text = plan_outputs[-1]

    # 2) 调用 LLM 生成代码
    try:
        llm_call = api_func if api_func else call_doubao
        result = llm_call(write_prompt(plan_text))
    except Exception as e:
        step["output"] = {"text": f"write：LLM 调用失败：{e}"}
        return

    # 3) 提取代码块
    code = extract_code(result)

    # 4) 写入输出
    step["output"] = {
        "text": result,
        "code": code
    }

    # 5) 写入上下文（供 refine/test/fix/profile/doc 使用）
    context["intermediate_results"].append({
        "type": "write",
        "text": result,
        "code": code
    })

    # 6) 写入事件流（供 VSCode 实时展示）
    events.append(create_event("write_output", {
        "text": result,
        "code": code
    }))
