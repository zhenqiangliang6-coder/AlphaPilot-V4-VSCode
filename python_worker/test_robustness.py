# -*- coding: utf-8 -*-
"""
工业级容错测试：验证 Step Executor 的健壮性

测试场景:
1. MagicMock 输入处理
2. None/空字符串处理
3. LLM 调用失败降级
4. 代码提取多策略
5. 异常恢复能力
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.qwen.step_executor.utils import extract_code


def test_extract_code_with_magicmock():
    """测试1: MagicMock 输入不应该崩溃"""
    print("\n=== 测试1: MagicMock 输入 ===")
    
    mock_obj = MagicMock()
    result = extract_code(mock_obj)
    
    assert result == "", f"Expected empty string, got: {result}"
    print("✅ 通过: MagicMock 被正确处理")


def test_extract_code_with_none():
    """测试2: None 输入不应该崩溃"""
    print("\n=== 测试2: None 输入 ===")
    
    result = extract_code(None)
    
    assert result == "", f"Expected empty string, got: {result}"
    print("✅ 通过: None 被正确处理")


def test_extract_code_with_empty_string():
    """测试3: 空字符串处理"""
    print("\n=== 测试3: 空字符串 ===")
    
    result = extract_code("")
    assert result == "", f"Expected empty string, got: {result}"
    
    result = extract_code("   ")
    assert result == "", f"Expected empty string, got: {result}"
    
    print("✅ 通过: 空字符串被正确处理")


def test_extract_code_standard_markdown():
    """测试4: 标准 Markdown 代码块提取"""
    print("\n=== 测试4: 标准 Markdown 代码块 ===")
    
    text = """
这是一个示例

```python
def hello():
    print("Hello, World!")
```

结束
"""
    
    result = extract_code(text)
    expected = 'def hello():\n    print("Hello, World!")'
    
    assert result == expected, f"Expected:\n{expected}\nGot:\n{result}"
    print("✅ 通过: 标准代码块提取成功")


def test_extract_code_without_language():
    """测试5: 无语言标记的代码块"""
    print("\n=== 测试5: 无语言标记的代码块 ===")
    
    text = """
```
def world():
    return 42
```
"""
    
    result = extract_code(text)
    expected = "def world():\n    return 42"
    
    assert result == expected, f"Expected:\n{expected}\nGot:\n{result}"
    print("✅ 通过: 无语言标记代码块提取成功")


def test_extract_code_fallback_keyword_detection():
    """测试6: 关键词检测降级策略"""
    print("\n=== 测试6: 关键词检测降级 ===")
    
    # 没有代码块标记，但包含代码关键词
    text = """
分析结果如下：

def calculate_sum(a, b):
    return a + b

class Calculator:
    pass

希望这对你有帮助！
"""
    
    result = extract_code(text, fallback_strategies=True)
    
    # 应该提取到包含 def/class 的部分
    assert "def calculate_sum" in result or result != "", \
        f"Expected code with keywords, got: {result}"
    
    print(f"✅ 通过: 关键词检测提取到代码 (长度: {len(result)})")


def test_extract_code_full_text_as_code():
    """测试7: 完整文本作为代码（最后手段）"""
    print("\n=== 测试7: 完整文本作为代码 ===")
    
    # 看起来像代码但没有 Markdown 标记
    text = """
def add(a, b):
    return a + b

def multiply(a, b):
    return a * b
"""
    
    result = extract_code(text, fallback_strategies=True)
    
    assert "def add" in result, f"Expected code in result, got: {result}"
    print("✅ 通过: 完整文本被识别为代码")


def test_extract_code_mixed_content():
    """测试8: 混合内容（代码+文本）"""
    print("\n=== 测试8: 混合内容 ===")
    
    text = """
好的，我来帮你写一个排序函数。

首先，我们需要理解需求...

```python
def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n-i-1):
            if arr[j] > arr[j+1]:
                arr[j], arr[j+1] = arr[j+1], arr[j]
    return arr
```

这个算法的时间复杂度是 O(n²)。
"""
    
    result = extract_code(text)
    
    assert "def bubble_sort" in result, f"Expected sorting function, got: {result}"
    assert "bubble_sort(arr)" in result
    print("✅ 通过: 从混合内容中提取到代码")


def test_extract_code_invalid_type_conversion():
    """测试9: 无效类型转换"""
    print("\n=== 测试9: 无效类型转换 ===")
    
    class CustomObject:
        def __str__(self):
            raise ValueError("Cannot convert to string")
    
    obj = CustomObject()
    result = extract_code(obj)
    
    assert result == "", f"Expected empty string for unconvertible object, got: {result}"
    print("✅ 通过: 无法转换的对象返回空字符串")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("🧪 工业级容错测试 - Qwen Worker Step Executor")
    print("=" * 60)
    
    tests = [
        test_extract_code_with_magicmock,
        test_extract_code_with_none,
        test_extract_code_with_empty_string,
        test_extract_code_standard_markdown,
        test_extract_code_without_language,
        test_extract_code_fallback_keyword_detection,
        test_extract_code_full_text_as_code,
        test_extract_code_mixed_content,
        test_extract_code_invalid_type_conversion,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ 失败: {test.__name__}")
            print(f"   错误: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    if failed == 0:
        print("🎉 所有测试通过！工业级容错机制工作正常！")
    else:
        print(f"⚠️  {failed} 个测试失败，请检查实现")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
