# -*- coding: utf-8 -*-
# step_executor/analyze_step.py — AlphaPilot OS v3.0
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - analyze_step 必须在 Worker 内执行
#    - 前端、Node API、VSCode 插件都不能分析用户需求
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - analyze 是整个执行链的起点
#    - analyze 必须输出结构化分析（供 plan_step 使用）
#
# 本模块负责：
# 1. 分析用户任务描述
# 2. 提取关键需求点
# 3. 写入上下文（供 plan_step 使用）
# ⭐ 4. 支持流式输出（实时展示 AI 思考过程）
# ⭐ 5. 支持人格配置（从 context.meta 读取）
# ---------------------------------------------------------

from ..doubao_api import call_doubao, call_doubao_stream
from .prompts import analyze_prompt
from ....worker_config import create_event, stream_chunk, stream_start, stream_end


def run_analyze_step(step, context, events, task_id=None):
    """
    analyze 步骤（工业级容错 + 流式输出 + 人格配置）
    ---------------------------------------------------------
    输入：
        - 用户任务描述（step["input"]["prompt"]）
    输出：
        - 自然语言分析（结构化）
    
    ⭐ 流式输出支持：
        - 通过 task_id 发送 stream_chunk 事件
        - 实时展示 AI 思考过程 (channel=reasoning)
    
    ⭐ 人格配置支持：
        - 从 context.meta 读取 persona 类型
        - 动态注入 System Prompt
    """

    # ===== 第0层：启动流式输出 =====
    if task_id:
        try:
            stream_start(task_id, "🔍 正在分析需求...", phase="analyze")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # ===== 第0.5层：⭐ 获取人格配置（豆包独立实现）=====
    persona_config = None
    try:
        meta = context.get("meta", {})
        persona_type = meta.get("persona", "engineer")  # 默认工程师人格
        
        # ⭐ 使用豆包自己的人格配置（不依赖 Qwen）
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
        # ⭐ 构建完整 prompt（含人格配置）
        if persona_config:
            system_prompt = persona_config.get("system_prompt", "")
            full_prompt = f"{system_prompt}\n\n---\n\n用户请求:\n{analyze_prompt(user_input)}"
        else:
            full_prompt = analyze_prompt(user_input)
        
        # ⭐ 使用流式调用
        if task_id:
            for chunk in call_doubao_stream(full_prompt):
                result += chunk
                # 实时发送到前端 (channel=reasoning)
                stream_chunk(task_id, chunk, phase="analyze", channel="reasoning")
        else:
            # 非流式模式（向后兼容）
            result = call_doubao(full_prompt)
        
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
