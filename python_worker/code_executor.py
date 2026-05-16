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
import multiprocessing
import queue


# =========================================================
# ① 单文件执行器（兼容旧逻辑）+ 超时保护
# =========================================================

def _execute_code_in_process(code: str, result_queue: multiprocessing.Queue):
    """
    在独立进程中执行代码，避免主进程被卡住
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

    result_queue.put(result)


def run_python(code: str, timeout: int = 10) -> dict:
    """
    执行单个 Python 代码字符串（带超时保护）
    
    Args:
        code: 要执行的 Python 代码
        timeout: 超时时间（秒），默认 10 秒
    
    Returns:
        dict: 包含 stdout, stderr, error 的结果字典
    """
    result_queue = multiprocessing.Queue()
    
    # 创建子进程执行代码
    process = multiprocessing.Process(
        target=_execute_code_in_process,
        args=(code, result_queue)
    )
    
    process.start()
    process.join(timeout=timeout)
    
    if process.is_alive():
        # 超时：强制终止进程
        process.terminate()
        process.join(timeout=2)
        
        if process.is_alive():
            process.kill()
            process.join()
        
        return {
            "stdout": "",
            "stderr": "",
            "error": f"⏱️ 代码执行超时（{timeout}秒），可能包含无限循环或阻塞操作"
        }
    
    # 正常完成：从队列获取结果
    try:
        result = result_queue.get_nowait()
        return result
    except queue.Empty:
        return {
            "stdout": "",
            "stderr": "",
            "error": "⚠️ 执行进程未返回结果（异常退出）"
        }


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
