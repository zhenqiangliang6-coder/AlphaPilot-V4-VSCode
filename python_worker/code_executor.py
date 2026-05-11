# -*- coding: utf-8 -*-
# code_executor.py — AlphaPilot OS v3.0
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - 所有代码执行必须在 Worker 内完成
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - 支持多文件协议 v3.0
#    - 支持 run_python（单文件）
#    - 支持 run_python_project（多文件）
#
# 本模块负责：
# 1. 安全执行 Python 代码（单文件）
# 2. 安全执行整个项目（多文件）
# 3. 捕获 stdout / stderr / error
# ---------------------------------------------------------

import sys
import io
import traceback
import types


# =========================================================
# ① 单文件执行器（兼容旧逻辑）
# =========================================================
def run_python(code: str) -> dict:
    """
    执行单个 Python 代码字符串
    """

    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()

    old_stdout = sys.stdout
    old_stderr = sys.stderr

    sys.stdout = stdout_buffer
    sys.stderr = stderr_buffer

    result = {"stdout": "", "stderr": "", "error": None}

    try:
        exec(code, {})
    except Exception:
        result["error"] = traceback.format_exc()

    sys.stdout = old_stdout
    sys.stderr = old_stderr

    result["stdout"] = stdout_buffer.getvalue()
    result["stderr"] = stderr_buffer.getvalue()

    return result


# =========================================================
# ② 多文件执行器（核心）
# =========================================================
def run_python_project(all_code_context: str) -> dict:
    """
    执行整个项目（多文件协议 v3.0）
    ---------------------------------------------------------
    输入：
        - write_step 输出的完整多文件协议文本
    """

    # 解析 # FILE: 块
    import re
    file_blocks = re.findall(
        r"# FILE:\s*([^\n]+)\n(.*?)(?=\n# (FILE|TEST|DOC|META|DEPENDS):|\Z)",
        all_code_context,
        re.S
    )

    if not file_blocks:
        return {"stdout": "", "stderr": "", "error": "未找到任何 # FILE: 块"}

    # 创建虚拟模块空间
    module_globals = {}

    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()

    old_stdout = sys.stdout
    old_stderr = sys.stderr

    sys.stdout = stdout_buffer
    sys.stderr = stderr_buffer

    error = None

    try:
        for path, code, _ in file_blocks:
            # 每个文件作为独立模块执行
            module = types.ModuleType(path)
            exec(code, module.__dict__)
            module_globals[path] = module

    except Exception:
        error = traceback.format_exc()

    sys.stdout = old_stdout
    sys.stderr = old_stderr

    return {
        "stdout": stdout_buffer.getvalue(),
        "stderr": stderr_buffer.getvalue(),
        "error": error
    }
