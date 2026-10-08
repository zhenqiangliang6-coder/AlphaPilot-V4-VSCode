# -*- coding: utf-8 -*-
# adapters.py — 步骤执行器依赖适配器实现
# ---------------------------------------------------------
# 将现有实现适配到接口，实现依赖注入
# ---------------------------------------------------------

from typing import Iterator, Dict, Any, List
from .interfaces import LLMClient, CodeExecutor, FileOpsParser, PythonCompiler


class QwenLLMClient(LLMClient):
    """Qwen LLM 客户端适配器"""
    
    def __init__(self):
        # 延迟导入，避免循环依赖
        from ..qwen_api import call_qwen, call_qwen_stream
        self._call = call_qwen
        self._call_stream = call_qwen_stream
    
    def call(self, prompt: str, **kwargs) -> str:
        return self._call(prompt, **kwargs)
    
    def call_stream(self, prompt: str, **kwargs) -> Iterator[str]:
        return self._call_stream(prompt, **kwargs)


class PythonCodeExecutor(CodeExecutor):
    """Python 代码执行器适配器"""
    
    def __init__(self):
        from ....code_executor import run_python
        self._execute = run_python
    
    def execute(self, code: str) -> Dict[str, Any]:
        return self._execute(code)


class V3FileOpsParser(FileOpsParser):
    """V3 文件操作解析器适配器"""
    
    def __init__(self):
        from ....file_ops import parse_fileops_v3
        self._parse = parse_fileops_v3
    
    def parse(self, response: str) -> List[Dict[str, Any]]:
        return self._parse(response)


class BuiltInPythonCompiler(PythonCompiler):
    """内置 Python 编译器适配器"""
    
    def compile(self, code: str, filename: str, mode: str = "exec") -> Any:
        return compile(code, filename, mode)


# ============================================================
# Mock 实现（用于测试）
# ============================================================

class MockLLMClient(LLMClient):
    """Mock LLM 客户端"""
    
    def __init__(self, response: str = "mock response"):
        self.response = response
        self.call_count = 0
        self.call_stream_count = 0
        self.prompts = []
    
    def call(self, prompt: str, **kwargs) -> str:
        self.call_count += 1
        self.prompts.append(prompt)
        return self.response
    
    def call_stream(self, prompt: str, **kwargs) -> Iterator[str]:
        self.call_stream_count += 1
        self.prompts.append(prompt)
        yield self.response


class MockCodeExecutor(CodeExecutor):
    """Mock 代码执行器"""
    
    def __init__(self, result: Dict[str, Any] = None):
        self.result = result or {
            "stdout": "",
            "stderr": "",
            "error": None,
            "exception": None
        }
        self.execute_count = 0
        self.codes = []
    
    def execute(self, code: str) -> Dict[str, Any]:
        self.execute_count += 1
        self.codes.append(code)
        return self.result


class MockFileOpsParser(FileOpsParser):
    """Mock 文件操作解析器"""
    
    def __init__(self, file_ops: List[Dict[str, Any]] = None):
        self.file_ops = file_ops or []
        self.parse_count = 0
        self.responses = []
    
    def parse(self, response: str) -> List[Dict[str, Any]]:
        self.parse_count += 1
        self.responses.append(response)
        return self.file_ops


class MockPythonCompiler(PythonCompiler):
    """Mock Python 编译器"""
    
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.compile_count = 0
        self.codes = []
    
    def compile(self, code: str, filename: str, mode: str = "exec") -> Any:
        self.compile_count += 1
        self.codes.append(code)
        if self.should_fail:
            raise SyntaxError("Mock syntax error")
        return compile(code, filename, mode)
