# -*- coding: utf-8 -*-
# step_executor/analyze_step.py
# ---------------------------------------------------------
# analyze 步骤：分析用户需求，提取关键点（工业级容错 + 流式输出版本）
# ---------------------------------------------------------

from ..qwen_api import call_qwen, call_qwen_stream
from .prompts import analyze_prompt
from ....worker_config import create_event, stream_chunk, stream_start, stream_end


def run_analyze_step(step, context, events, task_id=None):
    """
    analyze 步骤（工业级容错 + 流式输出）：
    - 输入：用户任务描述
    - 输出：需求分析（自然语言）
    
    ⭐ 新增：流式输出支持
    - 通过 task_id 发送 stream_chunk 事件
    - 实时展示 AI 思考过程 (channel=reasoning)
    
    容错策略:
    1. 验证输入存在且有效
    2. LLM 流式调用保护
    3. 输出保证
    """

    # ===== 第0层：启动流式输出 =====
    if task_id:
        try:
            stream_start(task_id, "🔍 正在分析需求...", phase="analyze")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # ===== 第1层防御：获取并验证用户输入 =====
    try:
        user_input = step.get("input", {}).get("prompt", "")

        if not isinstance(user_input, str) or not user_input.strip():
            error_msg = "analyze：未提供有效的任务描述。"
            if task_id:
                stream_chunk(task_id, error_msg, phase="analyze", channel="reasoning")
            step["output"] = {"text": error_msg}
            return
            
    except Exception as e:
        error_msg = f"analyze：获取输入时发生错误：{str(e)}"
        if task_id:
            stream_chunk(task_id, error_msg, phase="analyze", channel="reasoning")
        step["output"] = {"text": error_msg}
        return

    # ===== 第2层防御：流式调用 LLM 生成分析结果 =====
    result = ""
    llm_success = False
    
    try:
        prompt = analyze_prompt(user_input)
        
        # ⭐ 关键改动：使用流式调用
        if task_id:
            # 流式模式：逐块接收并转发
            for chunk in call_qwen_stream(prompt):
                result += chunk
                # 实时发送到前端 (channel=reasoning，因为analyze阶段主要是思考)
                stream_chunk(task_id, chunk, phase="analyze", channel="reasoning")
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
        error_msg = f"# LLM 调用超时\n无法分析任务: {user_input[:100]}"
        if task_id:
            stream_chunk(task_id, error_msg, phase="analyze", channel="reasoning")
        result = error_msg
    except Exception as e:
        error_msg = f"# LLM 调用失败: {str(e)}\n原始任务: {user_input[:100]}"
        if task_id:
            stream_chunk(task_id, error_msg, phase="analyze", channel="reasoning")
        result = error_msg

    # ===== 第3层防御：写入输出 =====
    step["output"] = {"text": result or "分析失败"}

    # ===== 第4层防御：写入上下文 =====
    try:
        context["intermediate_results"].append({
            "type": "analyze",
            "analysis": result or "",
            "llm_success": llm_success
        })
    except Exception as e:
        print(f"[ERROR] Failed to update context: {e}")

    # ===== 第5层防御：写入事件流 =====
    try:
        events.append(create_event("analyze_output", {
            "analysis": result or "",
            "llm_success": llm_success
        }))
    except Exception as e:
        print(f"[ERROR] Failed to append event: {e}")
    
    # ⭐ 结束流式输出
    if task_id:
        try:
            stream_end(task_id, phase="analyze")
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
