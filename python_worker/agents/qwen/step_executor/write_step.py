# -*- coding: utf-8 -*-
# step_executor/write_step.py
# ---------------------------------------------------------
# write 步骤：根据 plan 生成代码（工业级容错版本）
# ---------------------------------------------------------

from ..qwen_api import call_qwen
from .utils import extract_code
from .prompts import write_prompt
from ....worker_config import create_event


def run_write_step(step, context, events):
    """
    write 步骤（工业级容错）：
    - 输入：plan 步骤的规划
    - 输出：生成的 Python 代码
    
    容错策略:
    1. 验证 plan 输出存在且有效
    2. LLM 调用保护（超时、异常、非字符串返回）
    3. 代码提取保护（多策略降级）
    4. 输出保证（即使失败也返回有意义结果）
    """

    # ===== 第1层防御：获取并验证 plan 输出 =====
    try:
        plan_outputs = [
            item.get("plan", "")
            for item in context.get("intermediate_results", [])
            if item.get("type") == "plan" and item.get("plan")
        ]

        if not plan_outputs:
            step["output"] = {
                "text": "write：未找到 plan 步骤的规划内容。",
                "code": ""
            }
            return

        plan_text = plan_outputs[-1]
        
        # 验证规划文本有效性
        if not isinstance(plan_text, str) or not plan_text.strip():
            step["output"] = {
                "text": "write：plan 步骤的规划内容无效。",
                "code": ""
            }
            return
            
    except Exception as e:
        step["output"] = {
            "text": f"write：获取规划时发生错误：{str(e)}",
            "code": ""
        }
        return

    # ===== 第2层防御：调用 LLM 生成代码 =====
    result = None
    llm_success = False
    
    try:
        prompt = write_prompt(plan_text)
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
        
        llm_success = True
        
    except TimeoutError:
        print("[WARN] LLM 调用超时")
        result = f"# LLM 调用超时\n# 无法生成代码"
    except Exception as e:
        print(f"[ERROR] LLM 调用失败: {e}")
        result = f"# LLM 调用失败: {str(e)}"

    # ===== 第3层防御：提取代码块（多策略）=====
    code = ""
    
    try:
        if llm_success and result:
            code = extract_code(result, fallback_strategies=True)
            
            # 如果提取失败，但文本看起来像代码
            if not code and result:
                if any(kw in result for kw in ['def ', 'class ', 'import ']):
                    code = result.strip()
                    print("[INFO] Using full text as code (extraction failed)")
                    
    except Exception as e:
        print(f"[ERROR] Code extraction failed: {e}")
        code = ""

    # 最终保障
    if not code and result:
        code = "# 代码提取失败"

    # ===== 第4层防御：写入输出 =====
    step["output"] = {
        "text": result or "生成失败",
        "code": code,
        "llm_success": llm_success
    }

    # ===== 第5层防御：写入上下文 =====
    try:
        context["intermediate_results"].append({
            "type": "write",
            "text": result or "",
            "code": code,
            "llm_success": llm_success
        })
    except Exception as e:
        print(f"[ERROR] Failed to update context: {e}")

    # ===== 第6层防御：写入事件流 =====
    try:
        events.append(create_event("write_output", {
            "text": result or "",
            "code": code,
            "llm_success": llm_success
        }))
    except Exception as e:
        print(f"[ERROR] Failed to append event: {e}")
