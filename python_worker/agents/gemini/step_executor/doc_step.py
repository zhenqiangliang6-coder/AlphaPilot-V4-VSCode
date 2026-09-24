# -*- coding: utf-8 -*-
# step_executor/doc_step.py
# ---------------------------------------------------------
# doc 步骤：生成文档（Gemini 版 — 非核心步骤，异常降级）
# ---------------------------------------------------------

from .utils import extract_code
from .prompts import doc_prompt
from ..gemini_api import call_gemini
from ....worker_config import create_event


def run_doc_step(step, context, events, task_id=None):
    """
    doc 步骤（Gemini 版 — 非核心步骤，异常降级）：
    - 从 write 步骤获取代码
    - 生成 Markdown 文档
    - 生成带 docstring 的代码
    - ⭐ 异常时降级处理，不中断任务
    """
    write_outputs = [i["text"] for i in context["intermediate_results"] if i["type"] == "write"]
    if not write_outputs:
        step["output"] = {"text": "doc：未找到 write 步骤的代码。"}
        return

    code = extract_code(write_outputs[-1])
    
    try:
        markdown = call_gemini(doc_prompt(code))
    except Exception as e:
        print(f"⚠️ [Gemini Worker] doc 步骤 Markdown 生成失败（降级）: {e}")
        markdown = f"⚠️ 文档生成失败: {e}"

    try:
        docstring_code = call_gemini(f"请为下面代码添加 docstring：```python\n{code}\n```")
        documented = extract_code(docstring_code)
    except Exception as e:
        print(f"⚠️ [Gemini Worker] doc 步骤 docstring 生成失败（降级）: {e}")
        documented = code

    step["output"] = {
        "markdown": markdown,
        "documented_code": documented,
        "text": (
            "## 📄 Markdown 文档\n\n"
            + markdown
            + "\n\n---\n\n## 📝 带 docstring 的代码\n```python\n"
            + documented
            + "\n```"
        )
    }
