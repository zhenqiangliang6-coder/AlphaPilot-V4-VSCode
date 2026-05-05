# step_executor/utils.py（核心工具）
import re

def extract_code(text: str) -> str:
    pattern = r"```(?:python)?\s*(.*?)```"
    match = re.search(pattern, text, re.S)
    return match.group(1).strip() if match else ""

FAKE_PYTEST = """
class FakeRaises:
    def __init__(self, exc, match=None):
        self.exc = exc
        self.match = match

    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            raise AssertionError("Expected exception not raised")
        if not issubclass(exc_type, self.exc):
            raise AssertionError(f"Expected {self.exc}, got {exc_type}")
        if self.match and self.match not in str(exc):
            raise AssertionError(f"Expected message to contain '{self.match}'")
        return True

class pytest:
    @staticmethod
    def raises(exc, match=None):
        return FakeRaises(exc, match)
"""

FAKE_ENVIRONMENT = """
import builtins
from unittest.mock import MagicMock

import time, random, requests, os, sqlite3, subprocess

# ⭐ 修复：删除全局 mock，这些会污染整个 Python 进程
# 以下 mock 仅用于测试，不应在生产代码中使用
# builtins.open = MagicMock()
# time.sleep = MagicMock()
# random.random = MagicMock(return_value=0.5)
# requests.get = MagicMock()
# requests.post = MagicMock()
# os.remove = MagicMock()
# os.listdir = MagicMock(return_value=[])
# sqlite3.connect = MagicMock()
# subprocess.run = MagicMock()
"""
