from .utils import extract_code
from .prompts import doc_prompt
from ....code_executor import run_python
from ..doubao_api import call_doubao


def run_doc_step(step, context, events, api_func=None):
    """
    doc 步骤：生成代码文档
    
    参数:
        api_func: 可选的自定义 API 函数，如果不传则使用默认的 call_doubao
    """
    write_outputs = [i["text"] for i in context["intermediate_results"] if i["type"] == "write"]
    if not write_outputs:
        step["output"] = {"text": "doc：未找到 write 步骤的代码。"}
        return

    code = extract_code(write_outputs[-1])
    
    llm_call = api_func if api_func else call_doubao
    markdown = llm_call(doc_prompt(code))

    docstring_code = llm_call(f"请为下面代码添加 docstring：```python\n{code}\n```")
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
