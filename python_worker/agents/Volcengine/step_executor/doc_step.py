# -*- coding: utf-8 -*-
# step_executor/doc_step.py — AlphaPilot OS v3.0
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - 所有文档生成必须在 Worker 内完成
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - doc_step 必须输出 FileOps（唯一合法的文件操作方式）
#    - 文档必须使用多文件协议 v3.0（# DOC:）
#
# 本模块负责：
# 1. 为整个项目生成 Markdown 文档
# 2. 为代码生成 docstring 版本
# 3. 输出文档文件的 FileOps（docs/xxx.md）
# ---------------------------------------------------------

from ..doubao_api import call_doubao
from .prompts import doc_prompt, docstring_prompt
from ....worker_config import create_event
from ....file_ops import parse_fileops_v3


def run_doc_step(step, context, events, api_func=None):
    """
    doc 步骤（官方 + 智能增强版）
    ---------------------------------------------------------
    输入：
        - write_step 的多文件协议文本
    输出：
        - Markdown 文档（docs/README.md）
        - 带 docstring 的代码（可选）
        - FileOps（用于 Node API 写入文档）
    """

    # =========================================================
    # ① 获取 write_step 的多文件协议文本
    # =========================================================
    write_outputs = [
        item["text"]
        for item in context["intermediate_results"]
        if item["type"] == "write"
    ]

    if not write_outputs:
        step["output"] = {"text": "doc：未找到 write 步骤生成的代码或文件。"}
        return

    all_code_context = write_outputs[-1]

    # =========================================================
    # ② 调用 LLM 生成 Markdown 文档
    # =========================================================
    try:
        llm_call = api_func if api_func else call_doubao
        markdown = llm_call(doc_prompt(all_code_context))
    except Exception as e:
        markdown = f"# 文档生成失败\n\n错误：{e}"

    # =========================================================
    # ③ 调用 LLM 生成 docstring 版本代码
    # =========================================================
    try:
        docstring_text = llm_call(docstring_prompt(all_code_context))
    except Exception:
        docstring_text = "```python\n# docstring 生成失败\n```"

    # =========================================================
    # ④ 生成文档文件（多文件协议 v3.0）
    # =========================================================
    doc_protocol = f"# DOC: docs/README.md\n{markdown}"

    # 解析成 FileOps
    doc_file_ops = parse_fileops_v3(doc_protocol)

    # =========================================================
    # ⑤ 写入输出
    # =========================================================
    step["output"] = {
        "markdown": markdown,
        "docstring_code": docstring_text,
        "file_ops": doc_file_ops,
        "text": (
            "## 📄 Markdown 文档\n\n"
            + markdown
            + "\n\n---\n\n## 📝 带 docstring 的代码\n"
            + docstring_text
        )
    }

    # =========================================================
    # ⑥ 写入上下文（供 refine_step 使用）
    # =========================================================
    context["intermediate_results"].append({
        "type": "doc",
        "markdown": markdown,
        "docstring_code": docstring_text,
        "file_ops": doc_file_ops
    })

    # =========================================================
    # ⑦ 写入事件流（供 VSCode 实时展示）
    # =========================================================
    events.append(create_event("doc_output", {
        "markdown": markdown,
        "docstring_code": docstring_text,
        "file_ops": doc_file_ops
    }))
