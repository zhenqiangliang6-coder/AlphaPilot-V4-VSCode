# -*- coding: utf-8 -*-
# step_executor/write_step.py
# ---------------------------------------------------------
# write 步骤：根据 plan 生成代码
# ---------------------------------------------------------

from step_executor.qwen_api import call_qwen
from step_executor.utils import extract_code
from step_executor.prompts import write_prompt
from worker_config import create_event


def run_write_step(step, context, events):
    """
    write 步骤：
    - 输入：plan 步骤的规划
    - 输出：生成的 Python 代码
    """

    # 1) 获取 plan 步骤的输出（若无 plan 则回退到 analyze 输出 + 用户请求）
    meta = context.get("meta", {})
    user_request = meta.get("user_request", "")

    plan_outputs = [
        item["plan"]
        for item in context["intermediate_results"]
        if item["type"] == "plan"
    ]

    _step_input_prompt = step.get("input", {}).get("prompt", "")
    _has_vision_injection = "[图片分析结果]" in _step_input_prompt

    if not plan_outputs:
        # ⭐ v4.3: worker 预注入的视觉上下文优先级最高（高于 analyze 通用输出）
        if _has_vision_injection:
            plan_text = _step_input_prompt
            print(f"[INFO] write_step 使用 worker 注入的视觉上下文 prompt")
        else:
            analyze_outputs = [
                item.get("analysis", "") or item.get("text", "")
                for item in context.get("intermediate_results", [])
                if item.get("type") == "analyze"
            ]
            vision_outputs = [
                item.get("text", "")
                for item in context.get("intermediate_results", [])
                if item.get("type") == "vision_analysis"
            ]
            if vision_outputs:
                plan_text = f"# 图片分析结果\n{vision_outputs[-1]}\n\n# 用户原始请求\n{user_request}"
                print(f"[INFO] write_step 未找到 plan，回退使用 vision_analysis 输出 + 用户请求")
            elif analyze_outputs:
                plan_text = f"# 任务分析\n{analyze_outputs[-1]}\n\n# 用户原始请求\n{user_request}"
                print(f"[INFO] write_step 未找到 plan/vision，回退使用 analyze 输出 + 用户请求")
            else:
                plan_text = user_request or "请根据上下文生成内容"
                print(f"[INFO] write_step 未找到任何分析结果，回退使用用户请求")
    else:
        plan_text = plan_outputs[-1]

    # 2) 调用 LLM 生成代码
    try:
        result = call_qwen(write_prompt(plan_text))
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