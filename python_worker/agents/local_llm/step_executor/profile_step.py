# -*- coding: utf-8 -*-
# step_executor/profile_step.py
# ---------------------------------------------------------
# profile 步骤：性能分析
# - ⭐ v3.0：支持自定义 api_func（用于流式输出）
# ---------------------------------------------------------

from .utils import extract_code, FAKE_ENVIRONMENT
from .prompts import profile_prompt
from code_executor import run_python
from .qwen_api import call_qwen


def run_profile_step(step, context, events):
    """
    profile 步骤：
    - 输入：write 步骤的代码
    - 输出：性能分析和优化建议
    - ⭐ v3.0：支持通过 context['_custom_api_func'] 传入自定义 API 函数
    """
    
    write_outputs = [i["text"] for i in context["intermediate_results"] if i["type"] == "write"]
    if not write_outputs:
        step["output"] = {"text": "profile：未找到 write 步骤的代码。"}
        return

    code = extract_code(write_outputs[-1])
    
    # ⭐ v3.0：选择 API 调用函数
    api_func = context.get("_custom_api_func", call_qwen)
    
    analysis = api_func(profile_prompt(code))

    benchmark = run_python(FAKE_ENVIRONMENT + "\n\n" + code + """
import time
start = time.perf_counter()
funcs = [v for v in globals().values() if callable(v)]
if funcs:
    try: funcs[0]([])
    except: pass
end = time.perf_counter()
print("执行时间(ms):", (end-start)*1000)
""")

    step["output"] = {
        "text": analysis
        + "\n\n---\n\n性能测试（mock 环境）：\n"
        + f"stdout:\n{benchmark['stdout']}\n\nstderr:\n{benchmark['stderr']}\n\nerror:\n{benchmark['error']}"
    }
