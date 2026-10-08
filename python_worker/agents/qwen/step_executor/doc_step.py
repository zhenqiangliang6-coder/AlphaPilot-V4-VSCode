# -*- coding: utf-8 -*-
from .utils import extract_code
from .prompts import doc_prompt, docstring_prompt
from ....code_executor import run_python
from ..qwen_api import call_qwen
from ....worker_config import create_event, stream_start, stream_chunk, stream_end


def run_doc_step(step, context, events, task_id=None):
    """
    doc 步骤（工业级容错 + 流式输出）：生成文档和 docstring
    
    参数:
        step: 步骤定义
        context: 上下文对象
        events: 事件列表
        task_id: 任务 ID（可选，用于流式输出）
    """
    
    # ===== 第0层：启动流式输出 =====
    if task_id:
        try:
            stream_start(task_id, "📝 正在生成文档...", phase="doc")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # ===== 第1层防御：获取并验证 write 输出 =====
    try:
        write_outputs = [
            i.get("text", "")
            for i in context.get("intermediate_results", [])
            if i.get("type") == "write" and i.get("text")
        ]
        
        if not write_outputs:
            msg = "doc：未找到 write 步骤的代码。"
            if task_id:
                stream_chunk(task_id, msg, phase="doc", channel="reasoning")
                stream_end(task_id)
            step["output"] = {"text": msg}
            return
            
        write_text = write_outputs[-1]
        
    except Exception as e:
        msg = f"doc：获取代码时发生错误：{str(e)}"
        if task_id:
            stream_chunk(task_id, msg, phase="doc", channel="reasoning")
            stream_end(task_id)
        step["output"] = {"text": msg}
        return

    # ===== 第2层防御：提取代码 =====
    code = ""
    
    try:
        if isinstance(write_text, str):
            code = extract_code(write_text, fallback_strategies=True)
            
            if not code and write_text:
                if any(kw in write_text for kw in ['def ', 'class ', 'import ']):
                    code = write_text.strip()
                    
    except Exception as e:
        print(f"[ERROR] Code extraction failed: {e}")
        code = ""

    if not code:
        msg = "doc：无法提取有效代码。"
        if task_id:
            stream_chunk(task_id, msg, phase="doc", channel="reasoning")
            stream_end(task_id)
        step["output"] = {"text": msg}
        return

    # ===== 第3层防御：生成 Markdown 文档 =====
    markdown = ""
    
    try:
        prompt = doc_prompt(code)
        markdown = call_qwen(prompt)
        
        if markdown is None or not isinstance(markdown, str):
            markdown = str(markdown) if markdown else "# 文档生成失败"
            
    except Exception as e:
        print(f"[ERROR] Markdown generation failed: {e}")
        markdown = f"# 文档生成失败: {str(e)}"

    # ===== 第4层防御：生成带 docstring 的代码 =====
    documented = ""
    
    try:
        # ⭐ 修复：使用 docstring_prompt() 函数，而不是手写 prompt
        ds_prompt = docstring_prompt(code)
        docstring_code = call_qwen(ds_prompt)
        
        if docstring_code and isinstance(docstring_code, str):
            documented = extract_code(docstring_code, fallback_strategies=True)
            
            if not documented:
                documented = code  # 降级到原始代码
                
    except Exception as e:
        print(f"[ERROR] Docstring generation failed: {e}")
        documented = code  # 降级到原始代码

    if not documented:
        documented = code

    # ===== 第5层防御：构建输出 =====
    try:
        output_text = (
            "## 📄 Markdown 文档\n\n"
            + markdown
            + "\n\n---\n\n## 📝 带 docstring 的代码\n```python\n"
            + documented
            + "\n```"
        )
    except Exception as e:
        output_text = f"文档格式化失败: {str(e)}"

    step["output"] = {
        "markdown": markdown,
        "documented_code": documented,
        "text": output_text
    }
    
    # ===== 第6层：写入上下文和事件流 =====
    context["intermediate_results"].append({
        "type": "doc",
        "markdown": markdown,
        "documented_code": documented,
        "text": output_text
    })
    
    try:
        events.append(create_event("doc_output", {
            "markdown": markdown,
            "documented_code": documented,
            "text": output_text
        }))
    except Exception as e:
        print(f"[WARN] 创建事件失败: {e}")
    
    # ===== 第7层：结束流式输出 =====
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
