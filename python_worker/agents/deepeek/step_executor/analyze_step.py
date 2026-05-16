# -*- coding: utf-8 -*-
# step_executor/analyze_step.py
# ---------------------------------------------------------
# analyze 步骤：分析用户需求，提取关键点（v3.0 流式输出版）
# ---------------------------------------------------------

from ..deepseek_api import call_deepseek, call_deepseek_stream
from .prompts import analyze_prompt
from ....worker_config import create_event, stream_start, stream_chunk, stream_end


def run_analyze_step(step, context, events, task_id=None):
    """
    analyze 步骤：
    - 输入：用户任务描述
    - 输出：需求分析（自然语言）
    
    ⭐ v3.0 新增：
        - 支持流式输出（stream_start/stream_chunk/stream_end）
        - 使用 DeepSeek 独立的人格配置
        - 统一签名：task_id 参数
    
    参数:
        task_id: 任务 ID，用于流式输出
    """

    # ===== 第0.5层：⭐ 获取人格配置（DeepSeek独立实现）=====
    persona_config = None
    try:
        meta = context.get("meta", {})
        persona_type = meta.get("persona", "engineer")  # 默认工程师人格
        
        from ..personas import get_persona_config
        persona_config = get_persona_config(persona_type)
        
        print(f"🎨 analyze_step 使用人格: {persona_config['name']} ({persona_config['icon']})")
    except Exception as e:
        print(f"[WARN] 获取人格配置失败: {e}, 使用默认配置")
        persona_config = None

    # 1) 获取用户输入
    user_input = step["input"].get("prompt", "")

    if not user_input:
        step["output"] = {"text": "analyze：未提供任务描述。"}
        return

    # 2) 构建完整 prompt（含人格配置）
    full_prompt = analyze_prompt(user_input)
    if persona_config:
        full_prompt = f"{persona_config['system_prompt']}\n\n{full_prompt}"

    # 3) 启动流式输出
    result = ""
    if task_id:
        stream_start(task_id, "🔍 正在分析需求...", phase="analyze")

    # 4) 调用 LLM 生成分析结果（流式）
    try:
        if task_id:
            # 流式调用
            for chunk in call_deepseek_stream(full_prompt):
                result += chunk
                stream_chunk(task_id, chunk, phase="analyze", channel="reasoning")
        else:
            # 非流式调用（向后兼容）
            result = call_deepseek(full_prompt)
    except Exception as e:
        step["output"] = {"text": f"analyze：LLM 调用失败：{e}"}
        if task_id:
            stream_end(task_id)
        return

    # 5) 结束流式输出
    if task_id:
        stream_end(task_id)

    # 6) 写入输出
    step["output"] = {"text": result}

    # 7) 写入上下文（供 plan_step 使用）
    context["intermediate_results"].append({
        "type": "analyze",
        "analysis": result
    })

    # 8) 写入事件流（供 VSCode 实时展示）
    events.append(create_event("analyze_output", {
        "analysis": result
    }))
