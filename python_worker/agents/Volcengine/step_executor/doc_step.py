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
# ⭐ 4. 支持流式输出（实时展示文档生成过程）
# ⭐ 5. 支持人格配置（从 context.meta 读取）
# ---------------------------------------------------------

from ..doubao_api import call_doubao, call_doubao_stream
from .prompts import doc_prompt, docstring_prompt
from ....worker_config import create_event, stream_chunk, stream_start, stream_end
from ....file_ops import parse_fileops_v3


def run_doc_step(step, context, events, task_id=None):
    """
    doc 步骤（官方 + 智能增强版 + 流式输出 + 人格配置）
    ---------------------------------------------------------
    输入：
        - write_step 的多文件协议文本
    输出：
        - Markdown 文档（docs/README.md）
        - 带 docstring 的代码（可选）
        - FileOps（用于 Node API 写入文档）
    
    ⭐ 流式输出支持：
        - 通过 task_id 发送 stream_chunk 事件
        - 实时展示 AI 文档生成过程 (channel=content)
    
    ⭐ 人格配置支持：
        - 从 context.meta 读取 persona 类型
        - 动态注入 System Prompt
    """

    # ===== 第0层：启动流式输出 =====
    if task_id:
        try:
            stream_start(task_id, "📝 正在生成文档...", phase="doc")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # ===== 第0.5层：⭐ 获取人格配置（豆包独立实现）=====
    persona_config = None
    try:
        meta = context.get("meta", {})
        persona_type = meta.get("persona", "engineer")
        
        from ..personas import get_persona_config
        persona_config = get_persona_config(persona_type)
        
        print(f"🎨 doc_step 使用人格: {persona_config['name']}")
    except Exception as e:
        print(f"[WARN] 获取人格配置失败: {e}")
        persona_config = None

    # =========================================================
    # ① 获取 write_step 的多文件协议文本
    # =========================================================
    write_outputs = [
        item["text"]
        for item in context["intermediate_results"]
        if item["type"] == "write"
    ]

    if not write_outputs:
        msg = "doc：未找到 write 步骤生成的代码或文件。"
        if task_id:
            stream_chunk(task_id, msg, phase="doc", channel="reasoning")
        step["output"] = {"text": msg}
        
        if task_id:
            try:
                stream_end(task_id)
            except Exception as e:
                print(f"[WARN] stream_end 失败: {e}")
        return

    all_code_context = write_outputs[-1]

    # =========================================================
    # ② 调用 LLM 生成 Markdown 文档（流式输出）
    # =========================================================
    markdown = ""
    llm_success = False
    
    try:
        # ⭐ 构建完整 prompt（含人格配置）
        if persona_config:
            system_prompt = persona_config.get("system_prompt", "")
            full_prompt = f"{system_prompt}\n\n---\n\n用户请求:\n{doc_prompt(all_code_context)}"
        else:
            full_prompt = doc_prompt(all_code_context)

        # ⭐ 使用流式调用
        if task_id:
            for chunk in call_doubao_stream(full_prompt):
                markdown += chunk
                stream_chunk(task_id, chunk, phase="doc", channel="content")
        else:
            # 非流式模式（向后兼容）
            markdown = call_doubao(full_prompt)

        llm_success = True

    except Exception as e:
        error_msg = f"# 文档生成失败\n\n错误：{e}"
        markdown = error_msg
        
        if task_id:
            stream_chunk(task_id, error_msg, phase="doc", channel="reasoning")

    # =========================================================
    # ③ 调用 LLM 生成 docstring 版本代码（流式输出）
    # =========================================================
    docstring_text = ""
    
    try:
        # ⭐ 构建完整 prompt（含人格配置）
        if persona_config:
            system_prompt = persona_config.get("system_prompt", "")
            full_prompt = f"{system_prompt}\n\n---\n\n用户请求:\n{docstring_prompt(all_code_context)}"
        else:
            full_prompt = docstring_prompt(all_code_context)

        # ⭐ 使用流式调用
        if task_id:
            for chunk in call_doubao_stream(full_prompt):
                docstring_text += chunk
                stream_chunk(task_id, chunk, phase="doc", channel="content")
        else:
            # 非流式模式（向后兼容）
            docstring_text = call_doubao(full_prompt)

    except Exception:
        docstring_text = "``python\n# docstring 生成失败\n```"

    # =========================================================
    # ④ 生成文档文件（多文件协议 v3.0）
    # =========================================================
    doc_protocol = f"# DOC: docs/README.md\n{markdown}"

    # 解析成 FileOps
    doc_file_ops = []
    try:
        doc_file_ops = parse_fileops_v3(doc_protocol)
        print(f"✅ doc_step 生成 {len(doc_file_ops)} 个 FileOp")
        
        # ⭐ 写入 context（使用 final_file_ops 作为唯一真相源）
        if "final_file_ops" not in context:
            context["final_file_ops"] = []
        
        # 追加而非覆盖
        context["final_file_ops"].extend(doc_file_ops)
        
        # 向后兼容：仍然保留 file_ops 字段
        context["file_ops"] = context["final_file_ops"]
        
    except Exception as e:
        print(f"[ERROR] 解析 FileOps 失败: {e}")

    # =========================================================
    # ⑤ 写入输出
    # =========================================================
    step["output"] = {
        "markdown": markdown,
        "docstring_code": docstring_text,
        "file_ops": doc_file_ops,
        "llm_success": llm_success,
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
        "file_ops": doc_file_ops,
        "llm_success": llm_success
    })

    # =========================================================
    # ⑦ 写入事件流（供 VSCode 实时展示）
    # =========================================================
    events.append(create_event("doc_output", {
        "markdown": markdown,
        "docstring_code": docstring_text,
        "file_ops": doc_file_ops
    }))
    
    # ⭐ 结束流式输出
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
