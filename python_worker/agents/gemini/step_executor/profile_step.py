# -*- coding: utf-8 -*-
# step_executor/profile_step.py
# ---------------------------------------------------------
# profile 步骤：性能分析（Gemini 版 — 非核心步骤，异常降级）
# ---------------------------------------------------------

from .utils import extract_code, FAKE_ENVIRONMENT
from .prompts import profile_prompt
from ....code_executor import run_python
from ..gemini_api import call_gemini


def run_profile_step(step, context, events, task_id=None):
    """
    profile 步骤（Gemini 版 — 非核心步骤，异常降级）：
    - 从 write 步骤获取代码
    - 调用 LLM 进行性能分析
    - 执行性能基准测试
    - ⭐ 异常时降级处理，不中断任务
    """
    write_outputs = [i["text"] for i in context["intermediate_results"] if i["type"] == "write"]
    if not write_outputs:
        step["output"] = {"text": "profile：未找到 write 步骤的代码。"}
        return

    code = extract_code(write_outputs[-1])
    
    try:
        analysis = call_gemini(profile_prompt(code))
    except Exception as e:
        print(f"⚠️ [Gemini Worker] profile 步骤分析失败（降级）: {e}")
        analysis = f"⚠️ 性能分析失败: {e}"

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
