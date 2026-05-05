# -*- coding: utf-8 -*-
# code_executor.py
# ---------------------------------------------------------
# Python 代码执行器（用于 test / refine 步骤）
# ---------------------------------------------------------

import sys
import io
import traceback


def run_python(code: str) -> dict:
    """
    安全执行 Python 代码，返回 stdout / stderr / exception
    """

    # 捕获输出
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()

    # 保存原始 stdout/stderr
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    sys.stdout = stdout_buffer
    sys.stderr = stderr_buffer

    result = {
        "stdout": "",
        "stderr": "",
        "exception": None
    }

    try:
        exec(code, {})
    except Exception:
        result["exception"] = traceback.format_exc()

    # 恢复 stdout/stderr
    sys.stdout = old_stdout
    sys.stderr = old_stderr

    result["stdout"] = stdout_buffer.getvalue()
    result["stderr"] = stderr_buffer.getvalue()

    return result
