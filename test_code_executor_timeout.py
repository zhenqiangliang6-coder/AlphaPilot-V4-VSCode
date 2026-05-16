# -*- coding: utf-8 -*-
"""
测试 code_executor.py 的超时保护机制
"""

import sys
import os

# 确保 python_worker 根目录在 sys.path 中
current_dir = os.path.dirname(os.path.abspath(__file__))
python_worker_dir = os.path.join(current_dir, 'python_worker')
if python_worker_dir not in sys.path:
    sys.path.insert(0, python_worker_dir)

from code_executor import run_python


def test_normal_code():
    """测试正常代码执行"""
    print("=" * 60)
    print("🧪 测试 1: 正常代码执行")
    print("=" * 60)
    
    code = """
print("Hello, AlphaPilot!")
result = 2 + 3
print(f"2 + 3 = {result}")
"""
    
    result = run_python(code, timeout=5)
    print(f"✅ stdout: {result['stdout']}")
    print(f"✅ stderr: {result['stderr']}")
    print(f"✅ error: {result['error']}")
    print()


def test_infinite_loop():
    """测试无限循环（应触发超时）"""
    print("=" * 60)
    print("🧪 测试 2: 无限循环（应触发超时保护）")
    print("=" * 60)
    
    code = """
while True:
    pass
"""
    
    result = run_python(code, timeout=3)
    print(f"⏱️ stdout: {result['stdout']}")
    print(f"⏱️ stderr: {result['stderr']}")
    print(f"⏱️ error: {result['error']}")
    
    if "超时" in str(result.get('error', '')):
        print("✅ 超时保护生效！")
    else:
        print("❌ 超时保护未生效！")
    print()


def test_syntax_error():
    """测试语法错误"""
    print("=" * 60)
    print("🧪 测试 3: 语法错误")
    print("=" * 60)
    
    code = """
print("Hello"
"""
    
    result = run_python(code, timeout=5)
    print(f"✅ stdout: {result['stdout']}")
    print(f"✅ stderr: {result['stderr']}")
    print(f"✅ error: {result['error'] is not None}")
    print()


def test_sorting_function():
    """测试用户原始任务：排序函数"""
    print("=" * 60)
    print("🧪 测试 4: 排序函数（用户原始任务）")
    print("=" * 60)
    
    code = """
def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n-i-1):
            if arr[j] > arr[j+1]:
                arr[j], arr[j+1] = arr[j+1], arr[j]
    return arr

# 测试
test_list = [64, 34, 25, 12, 22, 11, 90]
sorted_list = bubble_sort(test_list.copy())
print(f"原始列表: {test_list}")
print(f"排序结果: {sorted_list}")
"""
    
    result = run_python(code, timeout=5)
    print(f"✅ stdout:\n{result['stdout']}")
    print(f"✅ stderr: {result['stderr']}")
    print(f"✅ error: {result['error']}")
    print()


if __name__ == "__main__":
    print("\n🚀 开始测试 code_executor.py 超时保护机制\n")
    
    test_normal_code()
    test_infinite_loop()
    test_syntax_error()
    test_sorting_function()
    
    print("=" * 60)
    print("✅ 所有测试完成！")
    print("=" * 60)
