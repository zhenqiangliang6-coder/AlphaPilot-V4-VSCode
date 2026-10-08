# -*- coding: utf-8 -*-
# interfaces.py — 步骤执行器依赖接口定义
# ---------------------------------------------------------
# 通过依赖注入解耦执行链，提高可测试性和可扩展性
# ---------------------------------------------------------

from abc import ABC, abstractmethod
from typing import Iterator, Dict, Any, List


class LLMClient(ABC):
    """LLM 客户端接口"""
    
    @abstractmethod
    def call(self, prompt: str, **kwargs) -> str:
        """
        同步调用 LLM
        
        参数:
            prompt: 提示词
            **kwargs: 其他参数（如 temperature, max_tokens）
        
        返回:
            str: LLM 响应文本
        """
        pass
    
    @abstractmethod
    def call_stream(self, prompt: str, **kwargs) -> Iterator[str]:
        """
        流式调用 LLM
        
        参数:
            prompt: 提示词
            **kwargs: 其他参数
        
        返回:
            Iterator[str]: 流式响应的迭代器
        """
        pass


class CodeExecutor(ABC):
    """代码执行器接口"""
    
    @abstractmethod
    def execute(self, code: str) -> Dict[str, Any]:
        """
        执行 Python 代码
        
        参数:
            code: Python 代码字符串
        
        返回:
            Dict[str, Any]: 执行结果，包含 stdout, stderr, error, exception
        """
        pass


class FileOpsParser(ABC):
    """文件操作解析器接口"""
    
    @abstractmethod
    def parse(self, response: str) -> List[Dict[str, Any]]:
        """
        解析 LLM 响应为文件操作列表
        
        参数:
            response: LLM 响应文本
        
        返回:
            List[Dict[str, Any]]: 文件操作列表
        """
        pass


class PythonCompiler(ABC):
    """Python 编译器接口"""
    
    @abstractmethod
    def compile(self, code: str, filename: str, mode: str = "exec") -> Any:
        """
        编译 Python 代码
        
        参数:
            code: Python 代码字符串
            filename: 文件名（用于错误信息）
            mode: 编译模式（exec, eval, single）
        
        返回:
            编译后的代码对象
        
        异常:
            SyntaxError: 语法错误
        """
        pass
