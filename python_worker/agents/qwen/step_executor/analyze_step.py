# -*- coding: utf-8 -*-
# step_executor/analyze_step.py
# ---------------------------------------------------------
# analyze 步骤：分析用户需求，提取关键点（工业级容错版本）
# ---------------------------------------------------------

from ..qwen_api import call_qwen
from .prompts import analyze_prompt
from ....worker_config import create_event


def run_analyze_step(step, context, events):
    """
    analyze 步骤（工业级容错）：
    - 输入：用户任务描述
    - 输出：需求分析（自然语言）
    
    容错策略:
    1. 验证输入存在且有效
    2. LLM 调用保护
    3. 输出保证
    """

    # ===== 第1层防御：获取并验证用户输入 =====
    try:
        user_input = step.get("input", {}).get("prompt", "")

        if not isinstance(user_input, str) or not user_input.strip():
            step["output"] = {"text": "analyze：未提供有效的任务描述。"}
            return
            
    except Exception as e:
        step["output"] = {"text": f"analyze：获取输入时发生错误：{str(e)}"}
        return

    # ===== 第2层防御：调用 LLM 生成分析结果 =====
    result = None
    
    try:
        prompt = analyze_prompt(user_input)
        result = call_qwen(prompt)
        
        # 验证返回值
        if result is None:
            raise ValueError("LLM 返回 None")
        
        if not isinstance(result, str):
            try:
                result = str(result)
            except:
                raise TypeError(f"LLM 返回非字符串类型: {type(result)}")
        
        if not result.strip():
            raise ValueError("LLM 返回空字符串")
            
    except TimeoutError:
        print("[WARN] LLM 调用超时")
        result = f"# LLM 调用超时\n无法分析任务: {user_input[:100]}"
    except Exception as e:
        print(f"[ERROR] LLM 调用失败: {e}")
        result = f"# LLM 调用失败: {str(e)}\n原始任务: {user_input[:100]}"

    # ===== 第3层防御：写入输出 =====
    step["output"] = {"text": result or "分析失败"}

    # ===== 第4层防御：写入上下文 =====
    try:
        context["intermediate_results"].append({
            "type": "analyze",
            "analysis": result or ""
        })
    except Exception as e:
        print(f"[ERROR] Failed to update context: {e}")

    # ===== 第5层防御：写入事件流 =====
    try:
        events.append(create_event("analyze_output", {
            "analysis": result or ""
        }))
    except Exception as e:
        print(f"[ERROR] Failed to append event: {e}")
