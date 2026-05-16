# -*- coding: utf-8 -*-
# step_executor/plan_step.py
# ---------------------------------------------------------
# plan 步骤：生成代码结构规划（v3.0 流式输出版）
# ---------------------------------------------------------

from ..deepseek_api import call_deepseek, call_deepseek_stream
from .prompts import plan_prompt
from ....worker_config import create_event, stream_start, stream_chunk, stream_end


def run_plan_step(step, context, events, task_id=None):
    """
    plan 步骤：
    - 输入：analyze 步骤的分析结果
    - 输出：代码结构规划（自然语言 + 伪代码）
    
    ⭐ v3.0 新增：
        - 支持流式输出
        - 使用 DeepSeek 独立的人格配置
        - 统一签名：task_id 参数
    
    参数:
        task_id: 任务 ID，用于流式输出
    """

    # ===== 第0.5层：⭐ 获取人格配置（DeepSeek独立实现）=====
    persona_config = None
    try:
        meta = context.get("meta", {})
        persona_type = meta.get("persona", "engineer")
        
        from ..personas import get_persona_config
        persona_config = get_persona_config(persona_type)
        
        print(f"🎨 plan_step 使用人格: {persona_config['name']}")
    except Exception as e:
        print(f"[WARN] 获取人格配置失败: {e}")
        persona_config = None

    # 1) 获取 analyze 步骤的输出
    analyze_outputs = [
        item["analysis"]
        for item in context["intermediate_results"]
        if item["type"] == "analyze"
    ]

    if not analyze_outputs:
        step["output"] = {"text": "plan：未找到 analyze 步骤的分析结果。"}
        return

    analysis_text = analyze_outputs[-1]

    # 2) 构建完整 prompt（含人格配置）
    full_prompt = plan_prompt(analysis_text)
    if persona_config:
        full_prompt = f"{persona_config['system_prompt']}\n\n{full_prompt}"

    # 3) 启动流式输出
    result = ""
    if task_id:
        stream_start(task_id, "📋 正在制定计划...", phase="plan")

    # 4) 调用 LLM 生成规划（流式）
    try:
        if task_id:
            for chunk in call_deepseek_stream(full_prompt):
                result += chunk
                stream_chunk(task_id, chunk, phase="plan", channel="reasoning")
        else:
            result = call_deepseek(full_prompt)
    except Exception as e:
        step["output"] = {"text": f"plan：LLM 调用失败：{e}"}
        if task_id:
            stream_end(task_id)
        return

    # 5) 结束流式输出
    if task_id:
        stream_end(task_id)

    # 6) 写入输出
    step["output"] = {"text": result}

    # 7) 写入上下文（供 write_step 使用）
    context["intermediate_results"].append({
        "type": "plan",
        "plan": result
    })

    # 8) 写入事件流
    events.append(create_event("plan_output", {
        "plan": result
    }))
