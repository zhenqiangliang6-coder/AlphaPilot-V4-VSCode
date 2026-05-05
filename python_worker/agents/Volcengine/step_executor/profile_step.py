# （mock-aware 性能分析）
from .utils import extract_code, FAKE_ENVIRONMENT
from .prompts import profile_prompt
from ....code_executor import run_python
from ..doubao_api import call_doubao


def run_profile_step(step, context, events, api_func=None):
    """
    profile 步骤：分析代码性能
    
    参数:
        api_func: 可选的自定义 API 函数，如果不传则使用默认的 call_doubao
    """
    write_outputs = [i["text"] for i in context["intermediate_results"] if i["type"] == "write"]
    if not write_outputs:
        step["output"] = {"text": "profile：未找到 write 步骤的代码。"}
        return

    code = extract_code(write_outputs[-1])
    
    llm_call = api_func if api_func else call_doubao
    analysis = llm_call(profile_prompt(code))

    benchmark = run_python(FAKE_ENVIRONMENT + "\n\n" + code + """
import time
start = time.perf_counter()
funcs = [v for v in globals().values() if callable(v)]
if funcs:
    try: funcs[0]([])
    except: pass
end = time.perf_counter()
print("执行时间 (ms):", (end-start)*1000)
""")

    step["output"] = {
        "text": analysis
        + "\n\n---\n\n性能测试（mock 环境）：\n"
        + f"stdout:\n{benchmark['stdout']}\n\nstderr:\n{benchmark['stderr']}\n\nerror:\n{benchmark['error']}"
    }
