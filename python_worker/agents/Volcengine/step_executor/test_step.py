# step_executor/test_step.py
# ---------------------------------------------------------
# 自动生成并运行 pytest 风格单元测试（使用 fake pytest）
# ---------------------------------------------------------

from .utils import extract_code, FAKE_PYTEST
from .prompts import test_prompt
from ....code_executor import run_python
from ....worker_config import create_event
from ..doubao_api import call_doubao


def run_test_step(step, context, events, api_func=None):
    """
    执行 test 步骤：
    - 从 write 步骤获取代码
    - 生成 pytest 风格测试代码（不 import pytest）
    - 注入 fake pytest（支持 pytest.raises）
    - 组合执行：fake pytest + 用户代码 + 测试代码
    
    参数:
        api_func: 可选的自定义 API 函数，如果不传则使用默认的 call_doubao
    """

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

    # 3) 让 Doubao 生成 pytest 风格测试代码（不 import pytest）
    llm_call = api_func if api_func else call_doubao
    test_code_text = llm_call(test_prompt(code))
    test_code = extract_code(test_code_text)

    if not test_code:
        step["output"] = {"text": "test：未能从 LLM 输出中提取到有效的测试代码。"}
        return

    # 4) 组合执行 fake pytest + 用户代码 + 测试代码
    full_code = FAKE_PYTEST + "\n\n" + code + "\n\n" + test_code
    test_result = run_python(full_code)

    # 5) 输出测试结果
    test_summary = (
        f"## 🧪 生成的测试代码\n"
        f"``python\n{test_code}\n```\n\n"
        f"## 📊 测试结果\n"
        f"stdout:\n{test_result.get('stdout', '')}\n\n"
        f"stderr:\n{test_result.get('stderr', '')}\n\n"
        f"error:\n{test_result.get('error', 'None')}\n"
    )

    step["output"] = {"text": test_summary}

    # 6) 写入 context
    context["intermediate_results"].append({
        "type": "test",
        "test_code": test_code,
        "test_result": test_result,
        "tested_code": code
    })
