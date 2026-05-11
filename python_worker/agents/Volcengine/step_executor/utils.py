# -*- coding: utf-8 -*-
# step_executor/utils.py — AlphaPilot OS v3.0
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - 所有代码解析、mock 环境、fake pytest 都必须在 Worker 内完成
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - extract_code 必须支持多文件协议 v3.0
#    - FAKE_ENVIRONMENT 必须隔离执行环境，不能污染真实 Python 进程
#
# 本模块负责：
# 1. 解析代码块（支持多文件协议）
# 2. 提供安全的 mock 执行环境
# 3. 提供 fake pytest（支持 assert / raises）
# ---------------------------------------------------------

import re


# =========================================================
# ① extract_code（智能增强版）
#    - 支持 ```python``` 代码块
#    - 支持 # FILE: 块
# =========================================================
def extract_code(text: str) -> str:
    """
    智能代码提取器（支持多文件协议）
    ---------------------------------------------------------
    优先级：
    1. ```python``` 代码块
    2. # FILE: 块（提取第一个文件）
    """

    # ① 提取 ```python``` 代码块
    pattern = r"```(?:python)?\s*(.*?)```"
    match = re.search(pattern, text, re.S)
    if match:
        return match.group(1).strip()

    # ② 提取 # FILE: 块
    file_pattern = r"# FILE:\s*[^\n]+\n(.*?)(?=\n# (FILE|TEST|DOC|META|DEPENDS):|\Z)"
    match = re.search(file_pattern, text, re.S)
    if match:
        return match.group(1).strip()

    return ""


# =========================================================
# ② fake pytest（官方）
# =========================================================
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


# =========================================================
# ③ FAKE_ENVIRONMENT（安全隔离版）
# =========================================================
FAKE_ENVIRONMENT = """
import builtins
from unittest.mock import MagicMock

import time, random, requests, os, sqlite3, subprocess

# ⭐ 安全隔离：mock 所有危险操作
builtins.open = MagicMock()
time.sleep = MagicMock()
random.random = MagicMock(return_value=0.5)
requests.get = MagicMock()
requests.post = MagicMock()
os.remove = MagicMock()
os.listdir = MagicMock(return_value=[])
sqlite3.connect = MagicMock()
subprocess.run = MagicMock()
"""
