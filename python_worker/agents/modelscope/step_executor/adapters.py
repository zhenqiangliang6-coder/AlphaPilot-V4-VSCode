# -*- coding: utf-8 -*-
# adapters.py — 依赖注入的具体实现
# ---------------------------------------------------------
# 将具体的 LLM、代码执行器、文件解析器封装为接口实现
# ---------------------------------------------------------

from typing import Iterator, Dict, Any, List
from .interfaces import LLMClient, CodeExecutor, FileOpsParser, PythonCompiler
from ..modelscope_api import call_modelscope, call_modelscope_stream
from ....code_executor import run_python
from ....file_ops import parse_fileops_v3


class ModelScopeLLMClient(LLMClient):
    """ModelScope LLM 客户端实现"""
    
    def call(self, prompt: str, **kwargs) -> str:
        """同步调用 ModelScope"""
        return call_modelscope(prompt, **kwargs)
    
    def call_stream(self, prompt: str, **kwargs) -> Iterator[str]:
        """流式调用 ModelScope"""
        return call_modelscope_stream(prompt, **kwargs)


class PythonCodeExecutor(CodeExecutor):
    """Python 代码执行器实现"""
    
    def execute(self, code: str) -> Dict[str, Any]:
        """执行 Python 代码"""
        return run_python(code)


class V3FileOpsParser(FileOpsParser):
    """FileOps v3 解析器实现"""
    
    def parse(self, response: str) -> List[Dict[str, Any]]:
        """解析 FileOps v3 响应"""
        return parse_fileops_v3(response)


class DefaultPythonCompiler(PythonCompiler):
    """默认 Python 编译器实现"""
    
    def compile(self, code: str, filename: str, mode: str = "exec") -> Any:
        """编译 Python 代码"""
        return compile(code, filename, mode)


# =========================================================
# Mock 实现（用于测试）
# =========================================================

class MockLLMClient(LLMClient):
    """Mock LLM 客户端（用于测试）"""
    
    def __init__(self, response: str = "mock response"):
        self.response = response
        self.call_count = 0
        self.prompts = []
    
    def call(self, prompt: str, **kwargs) -> str:
        self.call_count += 1
        self.prompts.append(prompt)
        return self.response
    
    def call_stream(self, prompt: str, **kwargs) -> Iterator[str]:
        self.call_count += 1
        self.prompts.append(prompt)
        yield self.response


class MockCodeExecutor(CodeExecutor):
    """Mock 代码执行器（用于测试）"""
    
    def __init__(self, result: Dict[str, Any] = None):
        self.result = result or {"stdout": "", "stderr": "", "error": "None"}
        self.execute_count = 0
    
    def execute(self, code: str) -> Dict[str, Any]:
        self.execute_count += 1
        return self.result


class MockFileOpsParser(FileOpsParser):
    """Mock 文件解析器（用于测试）"""
    
    def __init__(self, file_ops: List[Dict[str, Any]] = None):
        self.file_ops = file_ops or []
        self.parse_count = 0
    
    def parse(self, response: str) -> List[Dict[str, Any]]:
        self.parse_count += 1
        return self.file_ops


class MockPythonCompiler(PythonCompiler):
    """Mock Python 编译器（用于测试）"""
    
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.compile_count = 0
    
    def compile(self, code: str, filename: str, mode: str = "exec") -> Any:
        self.compile_count += 1
        if self.should_fail:
            raise SyntaxError("Mock syntax error")
        return compile(code, filename, mode)
