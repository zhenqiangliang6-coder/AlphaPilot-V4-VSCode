# -*- coding: utf-8 -*-
# step_executor/plan_step.py
# ---------------------------------------------------------
# plan 步骤：生成代码结构规划（工业级容错版本）
# ---------------------------------------------------------

from ..qwen_api import call_qwen
from .prompts import plan_prompt
from ....worker_config import create_event


def run_plan_step(step, context, events):
    """
    plan 步骤（工业级容错）：
    - 输入：analyze 步骤的分析结果
    - 输出：代码结构规划（自然语言 + 伪代码）
    
    容错策略:
    1. 验证 analyze 输出存在且有效
    2. LLM 调用保护
    3. 输出保证
    """

    # ===== 第1层防御：获取并验证 analyze 输出 =====
    try:
        analyze_outputs = [
            item.get("analysis", "")
            for item in context.get("intermediate_results", [])
            if item.get("type") == "analyze" and item.get("analysis")
        ]

        if not analyze_outputs:
            step["output"] = {"text": "plan：未找到 analyze 步骤的分析结果。"}
            return

        analysis = analyze_outputs[-1]
        
        if not isinstance(analysis, str) or not analysis.strip():
            step["output"] = {"text": "plan：analyze 步骤的分析结果无效。"}
            return
            
    except Exception as e:
        step["output"] = {"text": f"plan：获取分析结果时发生错误：{str(e)}"}
        return

    # ===== 第2层防御：调用 LLM 生成规划 =====
    result = None
    
    try:
        prompt = plan_prompt(analysis)
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
        result = f"# LLM 调用超时\n无法生成规划"
    except Exception as e:
        print(f"[ERROR] LLM 调用失败: {e}")
        result = f"# LLM 调用失败: {str(e)}"

    # ===== 第3层防御：写入输出 =====
    step["output"] = {"text": result or "规划生成失败"}

    # ===== 第4层防御：写入上下文 =====
    try:
        context["intermediate_results"].append({
            "type": "plan",
            "plan": result or ""
        })
    except Exception as e:
        print(f"[ERROR] Failed to update context: {e}")

    # ===== 第5层防御：写入事件流 =====
    try:
        events.append(create_event("plan_output", {
            "plan": result or ""
        }))
    except Exception as e:
        print(f"[ERROR] Failed to append event: {e}")
