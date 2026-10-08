# -*- coding: utf-8 -*-
# step_executor/analyze_step.py
# ---------------------------------------------------------
# analyze 步骤：分析用户需求，提取关键点（Gemini 版 — 工业级容错 + 流式输出 + 人格配置）
# ---------------------------------------------------------

from ..gemini_api import call_gemini, call_gemini_stream, call_gemini_with_persona
from .prompts import analyze_prompt
from ....worker_config import create_event, stream_chunk, stream_start, stream_end


def run_analyze_step(step, context, events, task_id=None):
    """
    analyze 步骤（Gemini 版 — 工业级容错 + 流式输出 + 人格配置）：
    - 输入：用户任务描述
    - 输出：需求分析（自然语言）
    
    ⭐ v2.6 新增：人格配置支持
    - 从 context.meta 读取 persona 类型
    - 动态注入 System Prompt
    - 工程师/创作者/对话三种人格切换
    
    ⭐ 流式输出支持
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
            stream_start(task_id, "🔍 Gemini 正在分析需求...", phase="analyze")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # ===== 第0.5层：⭐ 获取人格配置 =====
    persona_config = None
    try:
        meta = context.get("meta", {})
        persona_type = meta.get("persona", "engineer")  # 默认工程师人格
        
        # 导入人格配置模块
        from ..personas import get_persona_config
        persona_config = get_persona_config(persona_type)
        
        print(f"🎨 analyze_step 使用人格: {persona_config['name']} ({persona_config['icon']})")
    except Exception as e:
        print(f"[WARN] 获取人格配置失败: {e}, 使用默认配置")
        persona_config = None

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

    # ===== 第2层防御：流式调用 LLM 生成分析结果（带人格配置）=====
    result = ""
    llm_success = False
    
    try:
        prompt = analyze_prompt(user_input)
        
        # ⭐ 使用带人格配置的流式调用
        if task_id:
            if persona_config:
                print(f"🚀 使用人格配置进行流式调用: {persona_config['name']}")
                for chunk in call_gemini_with_persona(prompt, persona_config, use_stream=True):
                    result += chunk
                    stream_chunk(task_id, chunk, phase="analyze", channel="reasoning")
            else:
                for chunk in call_gemini_stream(prompt):
                    result += chunk
                    stream_chunk(task_id, chunk, phase="analyze", channel="reasoning")
        else:
            # 非流式模式（向后兼容）
            if persona_config:
                result = call_gemini_with_persona(prompt, persona_config, use_stream=False)
            else:
                result = call_gemini(prompt)
        
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
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
