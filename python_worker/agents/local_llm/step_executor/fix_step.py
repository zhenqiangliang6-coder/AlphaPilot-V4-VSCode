# -*- coding: utf-8 -*-
# step_executor/fix_step.py
# ---------------------------------------------------------
# fix 步骤：根据错误信息修复代码
# - ⭐ v3.0：支持自定义 api_func（用于流式输出）
# ---------------------------------------------------------

from .utils import extract_code, FAKE_ENVIRONMENT
from .prompts import fix_prompt
from code_executor import run_python
from .qwen_api import call_qwen


def run_fix_step(step, context, events):
    """
    fix 步骤：
    - 输入：write 步骤的代码和执行错误
    - 输出：修复后的代码
    - ⭐ v3.0：支持通过 context['_custom_api_func'] 传入自定义 API 函数
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

    # ⭐ v3.0：选择 API 调用函数
    api_func = context.get("_custom_api_func", call_qwen)

    fixed_text = api_func(fix_prompt(code, exec_result["error"]))
    fixed_code = extract_code(fixed_text)

    verify = run_python(FAKE_ENVIRONMENT + "\n\n" + fixed_code)

    step["output"] = {
        "text": fixed_text
        + "\n\n---\n\n验证结果：\n"
        + f"stdout:\n{verify['stdout']}\n\nstderr:\n{verify['stderr']}\n\nerror:\n{verify['error']}"
    }
