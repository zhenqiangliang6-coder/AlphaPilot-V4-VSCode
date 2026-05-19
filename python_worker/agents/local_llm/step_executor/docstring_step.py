# -*- coding: utf-8 -*-
# step_executor/docstring_step.py
# ---------------------------------------------------------
# Local LLM Worker v3.0 — docstring 步骤（v3.0 流式输出版本）
# - ⭐ v3.0：支持流式输出（task_id 参数）
# - ⭐ 与 Qwen Worker v2 完全对齐
# ---------------------------------------------------------

from .utils import extract_code
from .prompts import docstring_prompt
from worker_config import create_event, stream_chunk, stream_start, stream_end
from ..local_api import call_local_llm



def run_docstring_step(step, context, events, task_id=None):
    """
    docstring 步骤（v3.0）：
    - 输入：write 步骤的代码
    - 输出：带完整 docstring 的代码
    - ⭐ v3.0：支持流式输出（通过 task_id 参数）
    
    参数:
        step: 步骤定义
        context: 上下文对象
        events: 事件列表
        task_id: 任务 ID（可选，用于流式输出）
    """

    # ===== 0. 流式输出开始 =====
    if task_id:
        try:
            stream_start(task_id, "📝 正在添加 docstring...", phase="docstring")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")
    
    write_outputs = [i["text"] for i in context["intermediate_results"] if i["type"] == "write"]
    if not write_outputs:
        step["output"] = {"text": "docstring：未找到 write 步骤的代码。"}
        return

    code = extract_code(write_outputs[-1])
    
    # ⭐ v3.0：选择 API 调用函数
    api_func = context.get("_custom_api_func", call_local_llm)
    
    # 生成带 docstring 的代码（⭐ 支持流式输出）
    docstring_text = ""
    llm_success = False

    try:
        prompt = docstring_prompt(code)

        if task_id:
            # ⭐ 流式输出模式
            stream_chunk(task_id, "生成 docstring...\n", phase="docstring", channel="reasoning")
            
            # 注意：Local LLM 的 call_qwen 目前不支持真正的流式，这里先同步调用
            docstring_text = api_func(prompt)
            stream_chunk(task_id, docstring_text, phase="docstring", channel="content")
        else:
            # 同步调用模式
            docstring_text = api_func(prompt)

        if not docstring_text:
            raise ValueError("LLM 返回空字符串")

        llm_success = True

    except Exception as e:
        err = f"# LLM 调用失败: {e}"
        docstring_text = err
        if task_id:
            stream_chunk(task_id, err, phase="docstring", channel="reasoning")

    documented_code = extract_code(docstring_text)

    step["output"] = {
        "documented_code": documented_code,
        "text": (
            "## 📝 带 docstring 的代码\n```python\n"
            + documented_code
            + "\n```"
        ),
        "llm_success": llm_success
    }

    # ===== 7. 流式输出结束 =====
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
