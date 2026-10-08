# step_executor/utils.py（核心工具）
import re
from typing import Optional, Union


def extract_code(text: Union[str, object], fallback_strategies: bool = True) -> str:
    """
    从文本中提取代码块，具有工业级容错能力
    
    Args:
        text: 输入文本（可能是字符串、MagicMock或其他对象）
        fallback_strategies: 是否启用降级策略（默认True）
    
    Returns:
        提取的代码字符串，如果提取失败返回空字符串
        
    Strategies (按优先级):
        1. 标准 Python 代码块提取 (``python ... ```)
        2. 宽松代码块提取 (``` ... ```)
        3. 单行代码检测 (包含 def/class/import)
        4. 完整文本作为代码（最后手段）
    """
    # ===== 第1层防御：类型安全检查 =====
    if text is None:
        return ""
    
    # 处理 MagicMock 和其他非字符串对象
    if not isinstance(text, str):
        # 如果是 MagicMock，记录警告并返回空
        if hasattr(text, '_mock_name'):
            print(f"[WARN] extract_code received MagicMock object: {text._mock_name}")
            return ""
        
        # 尝试转换为字符串
        try:
            text = str(text)
        except Exception as e:
            print(f"[ERROR] Cannot convert to string: {e}")
            return ""
    
    # 空字符串检查
    if not text or not text.strip():
        return ""
    
    # ===== 第2层防御：多策略提取 =====
    
    # 策略1: 标准 Python 代码块
    pattern1 = r"```(?:python)?\s*(.*?)```"
    match = re.search(pattern1, text, re.S | re.IGNORECASE)
    if match:
        code = match.group(1).strip()
        if code:  # 确保不是空代码
            return code
    
    # 策略2: 宽松代码块（任何语言标记）
    pattern2 = r"```\w*\s*(.*?)```"
    match = re.search(pattern2, text, re.S)
    if match:
        code = match.group(1).strip()
        if code:
            return code
    
    # 策略3: 检测代码特征（包含 def/class/import）
    if fallback_strategies:
        lines = text.split('\n')
        code_lines = []
        in_code_block = False
        
        for line in lines:
            stripped = line.strip()
            # 检测代码开始
            if any(stripped.startswith(kw) for kw in ['def ', 'class ', 'import ', 'from ']):
                in_code_block = True
            
            if in_code_block:
                code_lines.append(line)
            
            # 检测代码结束（连续空行或明显文本）
            if in_code_block and stripped and not any(c in stripped for c in ['(', ')', ':', '{', '}', '[', ']', '=', '+', '-', '*', '/']):
                if len(code_lines) > 2:  # 至少收集了3行代码
                    break
        
        if code_lines:
            return '\n'.join(code_lines).strip()
    
    # 策略4: 如果文本看起来像代码（包含关键字），直接使用
    if fallback_strategies:
        code_keywords = ['def ', 'class ', 'import ', 'return ', 'if ', 'for ', 'while ', 'try:', 'except']
        if any(kw in text for kw in code_keywords):
            # 移除可能的 Markdown 格式符号
            cleaned = text.replace('**', '').replace('*', '').replace('# ', '')
            return cleaned.strip()
    
    # 最后手段：返回空（宁可失败也不要返回垃圾数据）
    print(f"[WARN] extract_code failed to extract code from text (length={len(text)})")
    return ""


def safe_extract_json(text: str) -> Optional[dict]:
    """
    安全地从文本中提取 JSON，具有容错能力
    
    Args:
        text: 输入文本
    
    Returns:
        解析后的字典，失败返回 None
    """
    import json
    
    if not isinstance(text, str):
        return None
    
    # 尝试直接解析
    try:
        return json.loads(text)
    except:
        pass
    
    # 尝试提取 JSON 代码块
    pattern = r"```(?:json)?\s*(.*?)```"
    match = re.search(pattern, text, re.S | re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except:
            pass
    
    # 尝试查找花括号包裹的内容
    pattern2 = r"\{.*\}"
    match = re.search(pattern2, text, re.S)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            pass
    
    return None


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
