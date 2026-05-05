# （mock-aware 修复）
from .utils import extract_code, FAKE_ENVIRONMENT
from .prompts import fix_prompt
from ....code_executor import run_python
from ..doubao_api import call_doubao


def run_fix_step(step, context, events, api_func=None):
    """
    fix 步骤：根据 test 步骤的错误信息修复代码
    
    参数:
        api_func: 可选的自定义 API 函数，如果不传则使用默认的 call_doubao
    """
    write_outputs = [i["text"] for i in context["intermediate_results"] if i["type"] == "write"]
    if not write_outputs:
        step["output"] = {"text": "fix：未找到 write 步骤的代码。"}
        return

    code = extract_code(write_outputs[-1])
    exec_result = run_python(FAKE_ENVIRONMENT + "\n\n" + code)

    if not exec_result["error"]:
        step["output"] = {"text": "fix：代码执行成功，无需修复。"}
        return

    llm_call = api_func if api_func else call_doubao
    fixed_text = llm_call(fix_prompt(code, exec_result["error"]))
    fixed_code = extract_code(fixed_text)

    verify = run_python(FAKE_ENVIRONMENT + "\n\n" + fixed_code)

    step["output"] = {
        "text": fixed_text
        + "\n\n---\n\n验证结果：\n"
        + f"stdout:\n{verify['stdout']}\n\nstderr:\n{verify['stderr']}\n\nerror:\n{verify['error']}"
    }
