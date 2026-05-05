# -*- coding: utf-8 -*-
# code_executor.py
# ---------------------------------------------------------
# AlphaPilot 核心执行引擎（开发者模式）
# 
# 架构信条：
#   Worker = 真相    ← 这里是真相的源头
#   Extension = 映射
#   Webview = 投影
#   协议 = 宪法
#
# 设计理念：
#   - 这是开发者模式的核心能力，不是安全风险
#   - 只有完整的执行能力，才能实现真正的智能体
#   - fix/profile/test/refine 步骤都依赖此能力
#   - 在受控的开发环境中运行，为创造美好未来而生
#
# 核心功能：
#   - 执行任意 Python 代码（开发者特权）
#   - 完整捕获 stdout / stderr / exception
#   - 支持 import、变量定义、函数调用
#   - 返回结构化执行结果
# ---------------------------------------------------------

import sys
import io
import traceback
import contextlib


def run_python(code: str) -> dict:
    """
    执行任意 Python 代码（开发者模式/完全信任模式）
    
    这是 AlphaPilot 智能体的核心能力：
    - fix 步骤：执行代码 → 发现错误 → 自动修复
    - profile 步骤：运行 benchmark → 测量性能
    - test 步骤：执行单元测试 → 验证正确性
    - refine 步骤：运行优化 → 对比效果
    
    参数:
        code: 要执行的 Python 代码字符串
    
    返回:
        dict: {
            "success": bool,      # 是否成功执行
            "stdout": str,        # 标准输出
            "stderr": str,        # 标准错误
            "error": str | None   # 异常堆栈（如果有）
        }
    
    使用场景:
        # 1. fix 步骤
        result = run_python("print(1/0)")  # 捕获 ZeroDivisionError
        
        # 2. profile 步骤
        result = run_python(benchmark_code)  # 性能测试
        
        # 3. test 步骤
        result = run_python(test_code)  # 运行测试
        
        # 4. refine 步骤
        result = run_python(optimized_code)  # 验证优化
    
    安全说明:
        ⚠️ 这是开发者模式的核心能力，仅在受控的开发环境中使用
        ✅ 我们相信开发者的智慧和判断力
        ✅ 为创造美好未来而设计，不是风险而是力量
        🚀 生产环境部署时，应由平台运维人员配置适当的隔离措施
    """

    # 捕获 stdout / stderr
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()

    # 执行环境（允许 import、变量、函数）
    # 这是智能体能力的源泉，必须保持完整
    exec_globals = {}
    exec_locals = {}

    try:
        with contextlib.redirect_stdout(stdout_buffer):
            with contextlib.redirect_stderr(stderr_buffer):
                # 🔥 核心能力：执行任意 Python 代码
                # 这是 fix/profile/test/refine 的基础
                # 不是 Bug，是 AlphaPilot 的灵魂所在
                exec(code, exec_globals, exec_locals)

        return {
            "success": True,
            "stdout": stdout_buffer.getvalue(),
            "stderr": stderr_buffer.getvalue(),
            "error": None
        }

    except Exception as e:
        # 捕获异常，但不阻止执行
        # 异常信息也是宝贵的反馈（用于 fix 步骤）
        return {
            "success": False,
            "stdout": stdout_buffer.getvalue(),
            "stderr": stderr_buffer.getvalue(),
            "error": traceback.format_exc()
        }