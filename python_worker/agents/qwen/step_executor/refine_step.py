# -*- coding: utf-8 -*-
# step_executor/refine_step.py
# ---------------------------------------------------------
# refine 步骤：执行代码 + 优化代码（工业级容错版本）
# ---------------------------------------------------------

from ..qwen_api import call_qwen
from .utils import extract_code, FAKE_ENVIRONMENT
from .prompts import optimize_prompt
from ....code_executor import run_python
from ....worker_config import create_event


def run_refine_step(step, context, events):
    """
    refine 步骤（工业级容错）：
    - 执行 write 步骤生成的代码
    - 根据执行结果优化代码
    - 多层防御机制确保不会崩溃
    
    容错策略:
    1. 输入验证：检查 write 输出是否存在且有效
    2. 执行保护：捕获代码执行异常，提供降级方案
    3. LLM 调用保护：处理超时、错误响应、非字符串返回
    4. 代码提取保护：多策略提取，失败时使用原始代码
    5. 输出保证：即使部分失败，也返回有意义的结果
    """

    # ===== 第1层防御：获取并验证 write 步骤的代码 =====
    try:
        write_outputs = [
            item.get("code", "")
            for item in context.get("intermediate_results", [])
            if item.get("type") == "write" and item.get("code")
        ]

        if not write_outputs:
            step["output"] = {
                "text": "refine：未找到 write 步骤生成的代码。",
                "optimized_code": "",
                "exec_summary": "No code to refine"
            }
            return

        code = write_outputs[-1]
        
        # 验证代码有效性
        if not isinstance(code, str) or not code.strip():
            step["output"] = {
                "text": "refine：write 步骤的代码无效（空或非字符串）。",
                "optimized_code": "",
                "exec_summary": "Invalid code from write step"
            }
            return
            
    except Exception as e:
        step["output"] = {
            "text": f"refine：获取代码时发生错误：{str(e)}",
            "optimized_code": "",
            "exec_summary": f"Error retrieving code: {e}"
        }
        return

    # ===== 第2层防御：执行代码（带超时和异常捕获）=====
    exec_summary = ""
    exec_success = False
    
    try:
        exec_result = run_python(FAKE_ENVIRONMENT + "\n\n" + code)
        
        # 验证执行结果
        if isinstance(exec_result, dict):
            stdout = exec_result.get('stdout', '')
            stderr = exec_result.get('stderr', '')
            error = exec_result.get('error', 'None')
            
            exec_summary = (
                f"stdout:\n{stdout}\n\n"
                f"stderr:\n{stderr}\n\n"
                f"error:\n{error}"
            )
            
            # 判断是否执行成功
            exec_success = (error == 'None' or error is None) and not stderr
            
        else:
            exec_summary = f"Unexpected exec result type: {type(exec_result)}"
            
    except TimeoutError:
        exec_summary = "代码执行超时（超过30秒）"
    except MemoryError:
        exec_summary = "代码执行内存溢出"
    except Exception as e:
        exec_summary = f"代码执行异常：{type(e).__name__}: {str(e)}"

    # ===== 第3层防御：调用 LLM 优化代码（带重试和验证）=====
    optimized_text = None
    llm_call_success = False
    
    try:
        # 构建优化提示
        prompt = optimize_prompt(code, exec_summary)
        
        # 调用 LLM
        optimized_text = call_qwen(prompt)
        
        # 验证返回值
        if optimized_text is None:
            raise ValueError("LLM 返回 None")
        
        if not isinstance(optimized_text, str):
            # 尝试转换
            try:
                optimized_text = str(optimized_text)
            except:
                raise TypeError(f"LLM 返回非字符串类型: {type(optimized_text)}")
        
        if not optimized_text.strip():
            raise ValueError("LLM 返回空字符串")
        
        llm_call_success = True
        
    except TimeoutError:
        print("[WARN] LLM 调用超时，使用原始代码")
        optimized_text = f"# LLM 调用超时\n# 保留原始代码\n\n{code}"
    except Exception as e:
        print(f"[ERROR] LLM 调用失败: {e}")
        # 降级策略：直接返回原始代码
        optimized_text = f"# LLM 调用失败: {str(e)}\n# 保留原始代码\n\n{code}"

    # ===== 第4层防御：提取优化后的代码（多策略）=====
    optimized_code = ""
    
    try:
        if llm_call_success and optimized_text:
            # 使用强化版的 extract_code（支持多策略）
            optimized_code = extract_code(optimized_text, fallback_strategies=True)
            
            # 如果提取失败，但有文本内容，尝试直接使用
            if not optimized_code and optimized_text:
                # 检查文本是否看起来像代码
                if any(kw in optimized_text for kw in ['def ', 'class ', 'import ']):
                    optimized_code = optimized_text.strip()
                    print("[INFO] Using full text as code (extraction failed but text looks like code)")
                    
    except Exception as e:
        print(f"[ERROR] Code extraction failed: {e}")
        optimized_code = ""

    # 最终保障：如果优化代码为空，使用原始代码
    if not optimized_code:
        optimized_code = code
        print("[INFO] Fallback to original code (optimization failed)")

    # ===== 第5层防御：写入输出（保证至少有一个有效结果）=====
    step["output"] = {
        "text": optimized_text or f"优化失败，保留原始代码",
        "optimized_code": optimized_code,
        "exec_summary": exec_summary,
        "original_code": code,
        "llm_success": llm_call_success,
        "exec_success": exec_success
    }

    # ===== 第6层防御：写入上下文（供后续步骤使用）=====
    try:
        context["intermediate_results"].append({
            "type": "refine",
            "original_code": code,
            "optimized_code": optimized_code,
            "exec_summary": exec_summary,
            "llm_success": llm_call_success,
            "exec_success": exec_success
        })
    except Exception as e:
        print(f"[ERROR] Failed to update context: {e}")

    # ===== 第7层防御：写入事件流（供 VSCode 实时展示）=====
    try:
        events.append(create_event("refine_output", {
            "original_code": code,
            "optimized_code": optimized_code,
            "exec_summary": exec_summary,
            "llm_success": llm_call_success,
            "exec_success": exec_success
        }))
    except Exception as e:
        print(f"[ERROR] Failed to append event: {e}")
