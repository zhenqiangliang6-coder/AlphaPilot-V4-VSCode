# -*- coding: utf-8 -*-
# step_executor/test_step.py
# ---------------------------------------------------------
# Local LLM Worker v3.0 — test 步骤（v3.0 流式输出版本）
# - ⭐ v3.0：支持流式输出（task_id 参数）
# - ⭐ 与 Qwen Worker v2 完全对齐
# ---------------------------------------------------------

from .utils import extract_code, FAKE_PYTEST
from .prompts import test_prompt
from code_executor import run_python
from worker_config import create_event, stream_chunk, stream_start, stream_end
from ..local_api import call_local_llm
  # 你已有的 local_api 封装


def run_test_step(step, context, events, task_id=None):
    """
    执行 test 步骤（v3.0）：
    - 从 write 步骤获取代码
    - 生成 pytest 风格测试代码（不 import pytest）
    - 注入 fake pytest（支持 pytest.raises）
    - 组合执行：fake pytest + 用户代码 + 测试代码
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
            stream_start(task_id, "🧪 正在生成并执行测试...", phase="test")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # 1) 找到 write 步骤生成的代码
    write_outputs = [
        item["text"]
        for item in context["intermediate_results"]
        if item["type"] == "write"
    ]

    if not write_outputs:
        step["output"] = {"text": "test：未找到 write 步骤的代码，无法生成测试用例。"}
        return

    # 2) 提取用户代码
    code = extract_code(write_outputs[-1])
    if not code:
        step["output"] = {"text": "test：write 步骤未提供可解析的代码块。"}
        return

    # 3) ⭐ v3.0：选择 API 调用函数
    api_func = context.get("_custom_api_func", call_local_llm)

    # 4) 让 LLM 生成 pytest 风格测试代码（⭐ 支持流式输出）
    test_code_text = ""
    llm_success = False

    try:
        prompt = test_prompt(code)

        if task_id:
            # ⭐ 流式输出模式
            stream_chunk(task_id, "生成测试代码...\n", phase="test", channel="reasoning")
            
            # 注意：Local LLM 的 call_local_llm 目前不支持真正的流式，这里先同步调用
            test_code_text = api_func(prompt)
            stream_chunk(task_id, test_code_text, phase="test", channel="content")
        else:
            # 同步调用模式
            test_code_text = api_func(prompt)

        if not test_code_text:
            raise ValueError("LLM 返回空字符串")

        llm_success = True

    except Exception as e:
        err = f"# LLM 调用失败: {e}"
        test_code_text = err
        if task_id:
            stream_chunk(task_id, err, phase="test", channel="reasoning")

    test_code = extract_code(test_code_text)

    if not test_code:
        step["output"] = {"text": "test：未能从 LLM 输出中提取到有效的测试代码。"}
        return

    # 5) 组合执行 fake pytest + 用户代码 + 测试代码
    full_code = FAKE_PYTEST + "\n\n" + code + "\n\n" + test_code
    test_result = run_python(full_code)

    # 6) 输出测试结果
    test_summary = (
        f"## 🧪 生成的测试代码\n"
        f"``python\n{test_code}\n```\n\n"
        f"## 📊 测试结果\n"
        f"stdout:\n{test_result['stdout']}\n\n"
        f"stderr:\n{test_result['stderr']}\n\n"
        f"error:\n{test_result['error']}\n"
    )

    step["output"] = {
        "text": test_summary,
        "llm_success": llm_success
    }

    # 7) 写入 context
    context["intermediate_results"].append({
        "type": "test",
        "test_code": test_code,
        "test_result": test_result,
        "tested_code": code
    })

    # ===== 8. 流式输出结束 =====
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
