# -*- coding: utf-8 -*-
"""
快速验证 extract_code 的容错能力
"""

import sys
import os

# 直接导入 utils.py（避免依赖其他模块）
sys.path.insert(0, os.path.dirname(__file__))

# 手动加载 utils 模块
import importlib.util
spec = importlib.util.spec_from_file_location("utils", "agents/qwen/step_executor/utils.py")
utils = importlib.util.module_from_spec(spec)
spec.loader.exec_module(utils)

extract_code = utils.extract_code

from unittest.mock import MagicMock

print("=" * 60)
print("🧪 快速验证 extract_code 容错能力")
print("=" * 60)

# 测试1: MagicMock
print("\n✅ 测试1: MagicMock 输入")
result = extract_code(MagicMock())
print(f"   结果: {repr(result)}")
assert result == "", f"Expected empty string, got: {result}"

# 测试2: None
print("\n✅ 测试2: None 输入")
result = extract_code(None)
print(f"   结果: {repr(result)}")
assert result == "", f"Expected empty string, got: {result}"

# 测试3: 空字符串
print("\n✅ 测试3: 空字符串")
result = extract_code("")
print(f"   结果: {repr(result)}")
assert result == "", f"Expected empty string, got: {result}"

# 测试4: 标准代码块
print("\n✅ 测试4: 标准 Markdown 代码块")
text = """
```python
def hello():
    print("Hello")
```
"""
result = extract_code(text)
print(f"   结果长度: {len(result)}")
print(f"   包含 'def hello': {'def hello' in result}")
assert "def hello" in result

# 测试5: 混合内容
print("\n✅ 测试5: 混合内容提取")
text = """
这是一个排序函数：

```python
def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n-i-1):
            if arr[j] > arr[j+1]:
                arr[j], arr[j+1] = arr[j+1], arr[j]
    return arr
```

时间复杂度 O(n²)
"""
result = extract_code(text)
print(f"   结果长度: {len(result)}")
print(f"   包含 'bubble_sort': {'bubble_sort' in result}")
assert "bubble_sort" in result

print("\n" + "=" * 60)
print("🎉 所有测试通过！extract_code 具备工业级容错能力！")
print("=" * 60)
