# -*- coding: utf-8 -*-
from .utils import extract_code
from .prompts import doc_prompt
from ....code_executor import run_python
from ..qwen_api import call_qwen
from ....worker_config import create_event


def run_doc_step(step, context, events):
    """
    doc 步骤（工业级容错）：生成文档和 docstring
    
    容错策略:
    1. 验证 write 输出
    2. LLM 调用保护（两次调用）
    3. 代码提取保护
    4. 输出保证
    """
    
    # ===== 第1层防御：获取并验证 write 输出 =====
    try:
        write_outputs = [
            i.get("text", "")
            for i in context.get("intermediate_results", [])
            if i.get("type") == "write" and i.get("text")
        ]
        
        if not write_outputs:
            step["output"] = {"text": "doc：未找到 write 步骤的代码。"}
            return
            
        write_text = write_outputs[-1]
        
    except Exception as e:
        step["output"] = {"text": f"doc：获取代码时发生错误：{str(e)}"}
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
        step["output"] = {"text": "doc：无法提取有效代码。"}
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
        docstring_prompt = f"请为下面代码添加 docstring：\n```python\n{code}\n```"
        docstring_code = call_qwen(docstring_prompt)
        
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
