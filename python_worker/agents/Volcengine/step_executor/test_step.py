# -*- coding: utf-8 -*-
# step_executor/test_step.py — AlphaPilot OS v3.0
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - 所有测试生成必须在 Worker 内部完成
#    - 前端、Node API、VSCode 插件都不能生成测试文件
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - test_step 必须输出 FileOps（唯一合法的文件操作方式）
#    - 测试文件必须使用多文件协议 v3.0（# TEST:）
#
# 本模块负责：
# 1. 根据 write_step 的代码自动生成 pytest 风格测试
# 2. 自动注入 fake pytest（支持 assert / raises）
# 3. 输出测试文件的 FileOps（tests/test_xxx.py）
# ---------------------------------------------------------

from ..doubao_api import call_doubao
from .utils import extract_code, FAKE_PYTEST
from .prompts import test_prompt
from ....code_executor import run_python
from ....worker_config import create_event
from ....file_ops import parse_fileops_v3


def run_test_step(step, context, events, api_func=None):
    """
    test 步骤（官方 + 智能增强版）
    ---------------------------------------------------------
    输入：
        - write_step 的多文件协议文本
    输出：
        - 自动生成的 pytest 测试文件（# TEST:）
        - FileOps（用于 Node API 写入 tests/ 目录）
    """

    # =========================================================
    # ① 获取 write_step 的多文件协议文本
    # =========================================================
    write_outputs = [
        item["text"]
        for item in context["intermediate_results"]
        if item["type"] == "write"
    ]

    if not write_outputs:
        step["output"] = {"text": "test：未找到 write 步骤的代码，无法生成测试用例。"}
        return

    write_text = write_outputs[-1]

    # =========================================================
    # ② 提取 write_step 中的“主代码块”
    #    - test_prompt 需要单文件代码作为输入
    #    - 所以我们提取第一个 ```python 代码块
    # =========================================================
    code = extract_code(write_text)

    if not code:
        step["output"] = {"text": "test：write 步骤未提供可解析的代码块。"}
        return

    # =========================================================
    # ③ 调用 LLM 生成 pytest 风格测试代码
    # =========================================================
    try:
        llm_call = api_func if api_func else call_doubao
        test_code_text = llm_call(test_prompt(code))
    except Exception as e:
        step["output"] = {"text": f"test：LLM 调用失败：{e}"}
        return

    test_code = extract_code(test_code_text)

    if not test_code:
        step["output"] = {"text": "test：未能从 LLM 输出中提取到有效的测试代码。"}
        return

    # =========================================================
    # ④ 组合执行 fake pytest + 用户代码 + 测试代码
    # =========================================================
    full_code = FAKE_PYTEST + "\n\n" + code + "\n\n" + test_code
    exec_result = run_python(full_code)

    exec_summary = (
        f"stdout:\n{exec_result['stdout']}\n\n"
        f"stderr:\n{exec_result['stderr']}\n\n"
        f"error:\n{exec_result['error']}"
    )

    # =========================================================
    # ⑤ 将测试代码包装成多文件协议 v3.0（# TEST:）
    # =========================================================
    test_protocol = f"# TEST: tests/test_generated.py\n{test_code}"

    # 解析成 FileOps
    test_file_ops = parse_fileops_v3(test_protocol)

    # =========================================================
    # ⑥ 写入输出
    # =========================================================
    step["output"] = {
        "text": test_protocol,
        "test_code": test_code,
        "file_ops": test_file_ops,
        "exec_summary": exec_summary
    }

    # =========================================================
    # ⑦ 写入上下文（供 refine_step 使用）
    # =========================================================
    context["intermediate_results"].append({
        "type": "test",
        "text": test_protocol,
        "test_code": test_code,
        "file_ops": test_file_ops,
        "exec_summary": exec_summary
    })

    # =========================================================
    # ⑧ 写入事件流（供 VSCode 实时展示）
    # =========================================================
    events.append(create_event("test_output", {
        "text": test_protocol,
        "test_code": test_code,
        "file_ops": test_file_ops,
        "exec_summary": exec_summary
    }))
