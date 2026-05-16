# -*- coding: utf-8 -*-
# step_executor/docstring_step.py
# ---------------------------------------------------------
# docstring 步骤：生成函数/类文档字符串（v3.0 流式输出版）
# ---------------------------------------------------------

from ..deepseek_api import call_deepseek, call_deepseek_stream
from .prompts import docstring_prompt
from ....worker_config import create_event, stream_start, stream_chunk, stream_end


def run_docstring_step(step, context, events, task_id=None):
    """
    docstring 步骤：
    - 输入：代码
    - 输出：带文档字符串的代码
    
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
        
        print(f"🎨 docstring_step 使用人格: {persona_config['name']}")
    except Exception as e:
        print(f"[WARN] 获取人格配置失败: {e}")
        persona_config = None

    # 1) 获取最新代码
    code_outputs = [
        item["text"]
        for item in context["intermediate_results"]
        if item["type"] in ["write", "refine", "fix"]
    ]

    if not code_outputs:
        step["output"] = {"text": "docstring：未找到代码。"}
        return

    code_text = code_outputs[-1]

    # 2) 构建完整 prompt（含人格配置）
    full_prompt = docstring_prompt(code_text)
    if persona_config:
        full_prompt = f"{persona_config['system_prompt']}\n\n{full_prompt}"

    # 3) 启动流式输出
    result = ""
    if task_id:
        stream_start(task_id, "📝 正在生成文档字符串...", phase="docstring")

    # 4) 调用 LLM 生成文档字符串（流式）
    try:
        if task_id:
            for chunk in call_deepseek_stream(full_prompt):
                result += chunk
                stream_chunk(task_id, chunk, phase="docstring", channel="reasoning")
        else:
            result = call_deepseek(full_prompt)
    except Exception as e:
        step["output"] = {"text": f"docstring：LLM 调用失败：{e}"}
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
        "type": "docstring",
        "text": result
    })

    # 8) 写入事件流
    events.append(create_event("docstring_output", {
        "text": result
    }))
