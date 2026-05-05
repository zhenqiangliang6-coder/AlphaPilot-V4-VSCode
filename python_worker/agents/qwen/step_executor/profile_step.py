# -*- coding: utf-8 -*-
# profile_step.py
# ---------------------------------------------------------
# 性能分析步骤（Profile Step - 工业级容错版本）
# ---------------------------------------------------------

from .utils import extract_code
from .prompts import profile_prompt
from ....code_executor import run_python
from ..qwen_api import call_qwen


def run_profile_step(task_id: str, step: dict, context: dict):
    """
    Profile Step（工业级容错）：让模型分析代码性能，并执行分析代码
    
    容错策略:
    1. 验证输入代码
    2. LLM 调用保护
    3. 代码提取保护
    4. 执行保护
    5. 输出保证
    """
    
    # ===== 第1层防御：验证输入 =====
    code = step.get("code", "")
    
    if not isinstance(code, str) or not code.strip():
        return {
            "profile_code": "",
            "result": {"error": "No code provided for profiling"},
            "success": False
        }

    # ===== 第2层防御：调用 LLM 生成性能分析代码 =====
    response = None
    llm_success = False
    
    try:
        prompt = profile_prompt.format(code=code)
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
        response = f"# LLM 调用超时\n# 无法生成性能分析代码"
    except Exception as e:
        print(f"[ERROR] LLM 调用失败: {e}")
        response = f"# LLM 调用失败: {str(e)}"

    # ===== 第3层防御：提取性能分析代码 =====
    profile_code = ""
    
    try:
        if llm_success and response:
            profile_code = extract_code(response, fallback_strategies=True)
            
            # 降级策略
            if not profile_code and response:
                if any(kw in response for kw in ['import cProfile', 'time.time()', 'perf_counter']):
                    profile_code = response.strip()
                    
    except Exception as e:
        print(f"[ERROR] Profile code extraction failed: {e}")
        profile_code = ""

    if not profile_code:
        # 生成默认的性能分析代码
        profile_code = f"""
import time

start = time.perf_counter()
# 执行原始代码
{code}
end = time.perf_counter()

print(f"Execution time: {{end - start:.4f}} seconds")
"""
        print("[INFO] Using default profiling code")

    # ===== 第4层防御：执行性能分析代码 =====
    result = {}
    exec_success = False
    
    try:
        result = run_python(profile_code)
        
        # 检查执行结果
        if isinstance(result, dict):
            error = result.get('error', 'None')
            exec_success = (error == 'None' or error is None)
        else:
            exec_success = True
            
    except Exception as e:
        result = {"error": f"Profiling execution failed: {str(e)}"}
        exec_success = False

    # ===== 第5层防御：返回结果 =====
    return {
        "profile_code": profile_code,
        "result": result,
        "llm_success": llm_success,
        "exec_success": exec_success,
        "success": exec_success
    }
