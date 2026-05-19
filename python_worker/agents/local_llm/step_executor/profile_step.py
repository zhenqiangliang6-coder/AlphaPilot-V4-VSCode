# -*- coding: utf-8 -*-
# step_executor/profile_step.py
# ---------------------------------------------------------
# Local LLM Worker v3.0 — profile 步骤（v3.0 流式输出版本）
# - ⭐ v3.0：支持流式输出（task_id 参数）
# - ⭐ 与 Qwen Worker v2 完全对齐
# ---------------------------------------------------------

from .utils import extract_code, FAKE_ENVIRONMENT
from .prompts import profile_prompt
from code_executor import run_python
from worker_config import create_event, stream_chunk, stream_start, stream_end
from ..local_api import call_local_llm



def run_profile_step(step, context, events, task_id=None):
    """
    profile 步骤（v3.0）：
    - 输入：write 步骤的代码
    - 输出：性能分析和优化建议
    - ⭐ v3.0：支持流式输出（通过 task_id 参数）
    
    参数:
        step: 步骤定义
        context: 上下文对象
        events: 事件列表
        task_id: 任务 ID（可选，用于流式输出）
    """

    # ===== 0. 流式输出开始 =====
    if task_id:
        try:
            stream_start(task_id, "⚡ 正在分析代码性能...", phase="profile")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")
    
    write_outputs = [i["text"] for i in context["intermediate_results"] if i["type"] == "write"]
    if not write_outputs:
        step["output"] = {"text": "profile：未找到 write 步骤的代码。"}
        return

    code = extract_code(write_outputs[-1])
    
    # ⭐ v3.0：选择 API 调用函数
    api_func = context.get("_custom_api_func", call_local_llm)
    
    # 生成性能分析（⭐ 支持流式输出）
    analysis = ""
    llm_success = False

    try:
        prompt = profile_prompt(code)

        if task_id:
            # ⭐ 流式输出模式
            stream_chunk(task_id, "分析性能...\n", phase="profile", channel="reasoning")
            
            # 注意：Local LLM 的 call_qwen 目前不支持真正的流式，这里先同步调用
            analysis = api_func(prompt)
            stream_chunk(task_id, analysis, phase="profile", channel="content")
        else:
            # 同步调用模式
            analysis = api_func(prompt)

        if not analysis:
            raise ValueError("LLM 返回空字符串")

        llm_success = True

    except Exception as e:
        err = f"# LLM 调用失败: {e}"
        analysis = err
        if task_id:
            stream_chunk(task_id, err, phase="profile", channel="reasoning")

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
        + f"stdout:\n{benchmark['stdout']}\n\nstderr:\n{benchmark['stderr']}\n\nerror:\n{benchmark['error']}",
        "llm_success": llm_success
    }

    # ===== 7. 流式输出结束 =====
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
