# -*- coding: utf-8 -*-
# step_executor/doc_step.py
# ---------------------------------------------------------
# doc 步骤：生成文档和 docstring
# - ⭐ v3.0：支持自定义 api_func（用于流式输出）
# ---------------------------------------------------------

from .utils import extract_code
from .prompts import doc_prompt
from code_executor import run_python
from .qwen_api import call_qwen


def run_doc_step(step, context, events):
    """
    doc 步骤：
    - 输入：write 步骤的代码
    - 输出：Markdown 文档和带 docstring 的代码
    - ⭐ v3.0：支持通过 context['_custom_api_func'] 传入自定义 API 函数
    """
    
    write_outputs = [i["text"] for i in context["intermediate_results"] if i["type"] == "write"]
    if not write_outputs:
        step["output"] = {"text": "doc：未找到 write 步骤的代码。"}
        return

    code = extract_code(write_outputs[-1])
    
    # ⭐ v3.0：选择 API 调用函数
    api_func = context.get("_custom_api_func", call_qwen)
    
    markdown = api_func(doc_prompt(code))

    docstring_code = api_func(f"请为下面代码添加 docstring：```python\n{code}\n```")
    documented = extract_code(docstring_code)

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
