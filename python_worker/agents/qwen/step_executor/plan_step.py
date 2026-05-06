# -*- coding: utf-8 -*-
# step_executor/plan_step.py
# ---------------------------------------------------------
# plan 步骤：生成代码结构规划（工业级容错 + 流式输出版本）
# ---------------------------------------------------------

from ..qwen_api import call_qwen, call_qwen_stream
from .prompts import plan_prompt
from ....worker_config import create_event, stream_chunk, stream_start, stream_end


def run_plan_step(step, context, events, task_id=None):
    """
    plan 步骤（工业级容错 + 流式输出）：
    - 输入：analyze 步骤的分析结果
    - 输出：代码结构规划（自然语言 + 伪代码）
    
    ⭐ 新增：流式输出支持
    - 通过 task_id 发送 stream_chunk 事件
    - 实时展示 AI 思考过程 (channel=reasoning)
    
    容错策略:
    1. 验证 analyze 输出存在且有效
    2. LLM 流式调用保护
    3. 输出保证
    """

    # ===== 第0层：启动流式输出 =====
    if task_id:
        try:
            stream_start(task_id, "📋 正在制定计划...", phase="plan")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # ===== 第1层防御：获取并验证 analyze 输出 =====
    try:
        analyze_outputs = [
            item.get("analysis", "")
            for item in context.get("intermediate_results", [])
            if item.get("type") == "analyze" and item.get("analysis")
        ]

        if not analyze_outputs:
            error_msg = "plan：未找到 analyze 步骤的分析结果。"
            if task_id:
                stream_chunk(task_id, error_msg, phase="plan", channel="reasoning")
            step["output"] = {"text": error_msg}
            return

        analysis = analyze_outputs[-1]
        
        if not isinstance(analysis, str) or not analysis.strip():
            error_msg = "plan：analyze 步骤的分析结果无效。"
            if task_id:
                stream_chunk(task_id, error_msg, phase="plan", channel="reasoning")
            step["output"] = {"text": error_msg}
            return
            
    except Exception as e:
        error_msg = f"plan：获取分析结果时发生错误：{str(e)}"
        if task_id:
            stream_chunk(task_id, error_msg, phase="plan", channel="reasoning")
        step["output"] = {"text": error_msg}
        return

    # ===== 第2层防御：流式调用 LLM 生成规划 =====
    result = ""
    llm_success = False
    
    try:
        prompt = plan_prompt(analysis)
        
        # ⭐ 关键改动：使用流式调用
        if task_id:
            # 流式模式：逐块接收并转发
            for chunk in call_qwen_stream(prompt):
                result += chunk
                # 实时发送到前端 (channel=reasoning，因为plan阶段主要是思考)
                stream_chunk(task_id, chunk, phase="plan", channel="reasoning")
        else:
            # 非流式模式（向后兼容）
            result = call_qwen(prompt)
        
        # 验证返回值
        if not result:
            raise ValueError("LLM 返回空字符串")
        
        if not isinstance(result, str):
            try:
                result = str(result)
            except:
                raise TypeError(f"LLM 返回非字符串类型: {type(result)}")
        
        llm_success = True
        
    except TimeoutError:
        error_msg = f"# LLM 调用超时\n无法生成规划"
        if task_id:
            stream_chunk(task_id, error_msg, phase="plan", channel="reasoning")
        result = error_msg
    except Exception as e:
        error_msg = f"# LLM 调用失败: {str(e)}"
        if task_id:
            stream_chunk(task_id, error_msg, phase="plan", channel="reasoning")
        result = error_msg

    # ===== 第3层防御：写入输出 =====
    step["output"] = {"text": result or "规划生成失败"}

    # ===== 第4层防御：写入上下文 =====
    try:
        context["intermediate_results"].append({
            "type": "plan",
            "plan": result or "",
            "llm_success": llm_success
        })
    except Exception as e:
        print(f"[ERROR] Failed to update context: {e}")

    # ===== 第5层防御：写入事件流 =====
    try:
        events.append(create_event("plan_output", {
            "plan": result or "",
            "llm_success": llm_success
        }))
    except Exception as e:
        print(f"[ERROR] Failed to append event: {e}")
    
    # ⭐ 结束流式输出
    if task_id:
        try:
            stream_end(task_id, phase="plan")
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
