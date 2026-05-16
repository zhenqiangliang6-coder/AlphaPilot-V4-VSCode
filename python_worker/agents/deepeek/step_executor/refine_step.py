# -*- coding: utf-8 -*-
# step_executor/refine_step.py
# ---------------------------------------------------------
# refine 步骤：优化和改进代码（v3.0 流式输出版）
# ---------------------------------------------------------

from ..deepseek_api import call_deepseek, call_deepseek_stream
from .prompts import refine_prompt
from ....worker_config import create_event, stream_start, stream_chunk, stream_end


def run_refine_step(step, context, events, task_id=None):
    """
    refine 步骤：
    - 输入：write 步骤生成的代码
    - 输出：优化后的代码
    
    ⭐ v3.0 新增：
        - 支持流式输出
        - 使用 DeepSeek 独立的人格配置
        - 更新 final_file_ops
        - 统一签名：task_id 参数
    """

    # ===== 第0.5层：⭐ 获取人格配置（DeepSeek独立实现）=====
    persona_config = None
    try:
        meta = context.get("meta", {})
        persona_type = meta.get("persona", "engineer")
        
        from ..personas import get_persona_config
        persona_config = get_persona_config(persona_type)
        
        print(f"🎨 refine_step 使用人格: {persona_config['name']}")
    except Exception as e:
        print(f"[WARN] 获取人格配置失败: {e}")
        persona_config = None

    # 1) 获取 write 步骤的输出
    write_outputs = [
        item["text"]
        for item in context["intermediate_results"]
        if item["type"] == "write"
    ]

    if not write_outputs:
        step["output"] = {"text": "refine：未找到 write 步骤的代码。"}
        return

    code_text = write_outputs[-1]

    # 2) 构建完整 prompt（含人格配置）
    full_prompt = refine_prompt(code_text)
    if persona_config:
        full_prompt = f"{persona_config['system_prompt']}\n\n{full_prompt}"

    # 3) 启动流式输出
    result = ""
    if task_id:
        stream_start(task_id, "✨ 正在优化代码...", phase="refine")

    # 4) 调用 LLM 优化代码（流式）
    try:
        if task_id:
            for chunk in call_deepseek_stream(full_prompt):
                result += chunk
                stream_chunk(task_id, chunk, phase="refine", channel="reasoning")
        else:
            result = call_deepseek(full_prompt)
    except Exception as e:
        step["output"] = {"text": f"refine：LLM 调用失败：{e}"}
        if task_id:
            stream_end(task_id)
        return

    # 5) 结束流式输出
    if task_id:
        stream_end(task_id)

    # 6) 写入输出
    step["output"] = {"text": result}

    # 7) 写入上下文
    context["intermediate_results"].append({
        "type": "refine",
        "text": result
    })

    # 8) 写入事件流
    events.append(create_event("refine_output", {
        "text": result
    }))
