# -*- coding: utf-8 -*-
# step_executor/write_step.py
# ---------------------------------------------------------
# write 步骤：根据 plan 生成代码
# - ⭐ v3.0：支持自定义 api_func（用于流式输出）
# ---------------------------------------------------------

from .qwen_api import call_qwen
from .utils import extract_code
from .prompts import write_prompt
from worker_config import create_event


def run_write_step(step, context, events):
    """
    write 步骤：
    - 模式 1（工程任务）：根据 plan 生成代码
    - 模式 2（对话任务）：直接返回 analyze 的结果或调用 LLM 生成回复
    - ⭐ v3.0：支持通过 context['_custom_api_func'] 传入自定义 API 函数
    """

    # ⭐ v3.0：选择 API 调用函数
    api_func = context.get("_custom_api_func", call_qwen)

    # 1) 检查是否有 plan 步骤（工程任务模式）
    plan_outputs = [
        item["plan"]
        for item in context["intermediate_results"]
        if item["type"] == "plan"
    ]

    if plan_outputs:
        # === 模式 1：工程任务（有 plan）===
        plan_text = plan_outputs[-1]

        # 调用 LLM 生成代码
        try:
            result = api_func(write_prompt(plan_text))
        except Exception as e:
            step["output"] = {"text": f"write：LLM 调用失败：{e}"}
            return

        # 提取代码块
        code = extract_code(result)

        # 写入输出
        step["output"] = {
            "text": result,
            "code": code
        }

        # 写入上下文（供 refine/test/fix/profile/doc 使用）
        context["intermediate_results"].append({
            "type": "write",
            "text": result,
            "code": code
        })

        # 写入事件流（供 VSCode 实时展示）
        events.append(create_event("write_output", {
            "text": result,
            "code": code
        }))
    else:
        # === 模式 2：对话任务（无 plan，直接使用 analyze 或调用 LLM）===
        
        # 检查是否有 analyze 步骤
        analyze_outputs = [
            item["analysis"]
            for item in context["intermediate_results"]
            if item["type"] == "analyze"
        ]

        if analyze_outputs:
            # 如果有 analyze，直接返回其结果（对话任务通常已经在 analyze 中完成）
            analysis_text = analyze_outputs[-1]
            
            # ⭐ 优化：如果 analyze 输出过长（超过 500 字符），调用 LLM 生成简洁回复
            if len(analysis_text) > 500:
                try:
                    # 调用 LLM 基于分析结果生成最终回复
                    result = api_func(f"请基于以下分析结果，用友好、自然的语言直接回答用户的问题：\n\n{analysis_text}")
                except Exception as e:
                    # 如果 LLM 调用失败，降级使用 analyze 的结果
                    result = analysis_text
            else:
                # analyze 输出较短，直接使用
                result = analysis_text
        else:
            # 既没有 plan 也没有 analyze，直接调用 LLM 生成回复
            user_input = step["input"].get("prompt", "")
            try:
                result = api_func(user_input)
            except Exception as e:
                step["output"] = {"text": f"write：LLM 调用失败：{e}"}
                return

        # 写入输出（对话任务不提取代码）
        step["output"] = {
            "text": result
        }

        # 写入上下文
        context["intermediate_results"].append({
            "type": "write",
            "text": result
        })

        # 写入事件流
        events.append(create_event("write_output", {
            "text": result
        }))
