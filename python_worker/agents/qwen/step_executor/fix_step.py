# -*- coding: utf-8 -*-
# fix_step.py
# ---------------------------------------------------------
# 修复步骤（Fix Step - 工业级容错版本）
# 根据错误信息让模型修复代码，然后执行修复后的代码
# ---------------------------------------------------------

from .utils import extract_code, FAKE_ENVIRONMENT
from .prompts import fix_prompt
from ....code_executor import run_python
from ..qwen_api import call_qwen


def run_fix_step(task_id: str, step: dict, context: dict):
    """
    修复代码（Fix Step - 工业级容错）
    
    容错策略:
    1. 验证输入参数（原始代码和错误信息）
    2. LLM 调用保护
    3. 代码提取保护
    4. 代码执行保护
    5. 输出保证
    """
    
    # ===== 第1层防御：验证输入 =====
    original_code = step.get("code", "")
    error_message = step.get("error", "")
    
    if not isinstance(original_code, str) or not original_code.strip():
        return {
            "fixed_code": "",
            "result": {"error": "No original code provided"},
            "success": False
        }
    
    if not isinstance(error_message, str):
        error_message = str(error_message)

    # ===== 第2层防御：生成修复提示词并调用 LLM =====
    response = None
    llm_success = False
    
    try:
        prompt = fix_prompt.format(
            code=original_code,
            error=error_message
        )
        
        response = call_qwen(prompt)
        
        # 验证返回值
        if response is None:
            raise ValueError("LLM 返回 None")
        
        if not isinstance(response, str):
            try:
                response = str(response)
            except:
                raise TypeError(f"LLM 返回非字符串类型: {type(response)}")
        
        if not response.strip():
            raise ValueError("LLM 返回空字符串")
        
        llm_success = True
        
    except TimeoutError:
        print("[WARN] LLM 调用超时")
        response = f"# LLM 调用超时\n{original_code}"
    except Exception as e:
        print(f"[ERROR] LLM 调用失败: {e}")
        response = f"# LLM 调用失败: {str(e)}\n{original_code}"

    # ===== 第3层防御：提取修复后的代码 =====
    fixed_code = ""
    
    try:
        if llm_success and response:
            fixed_code = extract_code(response, fallback_strategies=True)
            
            # 降级策略
            if not fixed_code and response:
                if any(kw in response for kw in ['def ', 'class ', 'import ']):
                    fixed_code = response.strip()
                    
    except Exception as e:
        print(f"[ERROR] Code extraction failed: {e}")
        fixed_code = ""

    # 最终保障
    if not fixed_code:
        fixed_code = original_code
        print("[INFO] Fallback to original code (fix extraction failed)")

    # ===== 第4层防御：执行修复后的代码 =====
    result = {}
    exec_success = False
    
    try:
        result = run_python(FAKE_ENVIRONMENT + "\n\n" + fixed_code)
        
        # 检查执行结果
        if isinstance(result, dict):
            error = result.get('error', 'None')
            exec_success = (error == 'None' or error is None)
        else:
            exec_success = True
            
    except Exception as e:
        result = {"error": f"Execution failed: {str(e)}"}
        exec_success = False

    # ===== 第5层防御：返回结果 =====
    return {
        "fixed_code": fixed_code,
        "result": result,
        "llm_success": llm_success,
        "exec_success": exec_success,
        "success": llm_success and exec_success
    }
