# -*- coding: utf-8 -*-
"""
AlphaPilot OS v2.7 多文件 FileOps 协议测试脚本（简化版）

直接测试 # FILE: 协议解析逻辑,避免复杂导入
"""

import re
from typing import List, Dict, Any


def _parse_multi_file_protocol(text: str, intent: str = "write_code") -> List[Dict[str, Any]]:
    """
    解析 LLM 输出中的 # FILE: 协议
    
    格式:
    # FILE: <相对路径>
    <代码内容>
    
    # FILE: <相对路径>
    <代码内容>
    """
    file_ops = []
    
    # 正则匹配: # FILE: path\ncontent (直到下一个 # FILE: 或结尾)
    pattern = r'# FILE:\s*(.+?)\n(.*?)(?=\n# FILE:|$)'
    matches = re.findall(pattern, text, re.DOTALL)
    
    for path, content in matches:
        path = path.strip()
        content = content.strip()
        
        # 跳过空文件
        if not content:
            continue
        
        # 推断语言
        ext = path.split('.')[-1] if '.' in path else ''
        language_map = {
            'py': 'python',
            'js': 'javascript',
            'ts': 'typescript',
            'jsx': 'javascript',
            'tsx': 'typescript',
            'java': 'java',
            'cpp': 'cpp',
            'c': 'c',
            'go': 'go',
            'rs': 'rust',
            'html': 'html',
            'css': 'css',
            'json': 'json',
            'md': 'markdown',
        }
        language = language_map.get(ext, 'text')
        
        file_ops.append({
            'action': 'create' if intent == 'write_code' else 'modify',
            'path': path,
            'type': 'file',
            'content': content,
            'language': language,
            'reason': 'LLM 生成的模块文件',
            'meta': {
                'from_step': 'write' if intent == 'write_code' else 'refine',
                'intent': intent
            }
        })
    
    return file_ops


def test_parse_multi_file_protocol():
    """测试 # FILE: 协议解析器"""
    print("=" * 60)
    print("测试1: 解析 # FILE: 协议")
    print("=" * 60)
    
    # 模拟 LLM 输出（多文件）
    llm_output = """
让我生成排序算法模块...

# FILE: sorter/__init__.py
from .sort_engine import sort

# FILE: sorter/algorithms.py
def bubble_sort(data, reverse=False):
    n = len(data)
    for i in range(n):
        for j in range(0, n - i - 1):
            if (not reverse and data[j] > data[j + 1]) or (reverse and data[j] < data[j + 1]):
                data[j], data[j + 1] = data[j + 1], data[j]
    return data

def quick_sort(data, reverse=False):
    def _quick_sort(arr):
        if len(arr) <= 1:
            return arr
        pivot = arr[len(arr) // 2]
        left = [x for x in arr if x < pivot]
        middle = [x for x in arr if x == pivot]
        right = [x for x in arr if x > pivot]
        return _quick_sort(left) + middle + _quick_sort(right)
    result = _quick_sort(data)
    if reverse:
        result.reverse()
    return result

# FILE: sorter/sort_engine.py
from .algorithms import bubble_sort, quick_sort

def sort(data, algorithm='auto', reverse=False):
    if algorithm == 'bubble':
        return bubble_sort(data, reverse)
    elif algorithm == 'quick':
        return quick_sort(data, reverse)
    else:
        return bubble_sort(data, reverse)
"""
    
    # 解析
    file_ops = _parse_multi_file_protocol(llm_output, intent="write_code")
    
    # 验证
    print(f"\n✅ 解析到 {len(file_ops)} 个 FileOp:")
    for op in file_ops:
        print(f"   - {op['action']}: {op['path']} ({len(op['content'])} bytes)")
    
    # 断言
    assert len(file_ops) == 3, f"期望3个FileOp,实际{len(file_ops)}个"
    assert file_ops[0]['path'] == "sorter/__init__.py"
    assert file_ops[1]['path'] == "sorter/algorithms.py"
    assert file_ops[2]['path'] == "sorter/sort_engine.py"
    
    print("\n✅ 测试1通过: # FILE: 协议解析成功")
    return True


def test_single_file_fallback():
    """测试单文件降级逻辑"""
    print("\n" + "=" * 60)
    print("测试2: 单文件降级逻辑")
    print("=" * 60)
    
    # 模拟 LLM 输出（无 # FILE: 协议）
    llm_output = """
def bubble_sort(data):
    n = len(data)
    for i in range(n):
        for j in range(0, n - i - 1):
            if data[j] > data[j + 1]:
                data[j], data[j + 1] = data[j + 1], data[j]
    return data
"""
    
    # 解析
    file_ops = _parse_multi_file_protocol(llm_output, intent="write_code")
    
    # 验证：应该返回空列表（触发降级）
    assert len(file_ops) == 0, f"期望0个FileOp,实际{len(file_ops)}个"
    
    print("\n✅ 测试2通过: 单文件降级逻辑正常")
    return True


def test_empty_file_skip():
    """测试空文件跳过逻辑"""
    print("\n" + "=" * 60)
    print("测试3: 空文件跳过逻辑")
    print("=" * 60)
    
    # 模拟 LLM 输出（包含空文件）
    llm_output = """
# FILE: sorter/__init__.py
from .sort_engine import sort

# FILE: sorter/empty.py

# FILE: sorter/algorithms.py
def bubble_sort(data):
    return data
"""
    
    # 解析
    file_ops = _parse_multi_file_protocol(llm_output, intent="write_code")
    
    # 验证：应该跳过空文件
    assert len(file_ops) == 2, f"期望2个FileOp,实际{len(file_ops)}个"
    assert file_ops[0]['path'] == "sorter/__init__.py"
    assert file_ops[1]['path'] == "sorter/algorithms.py"
    
    print("\n✅ 测试3通过: 空文件跳过逻辑正常")
    return True


def main():
    """运行所有测试"""
    print("\n🚀 AlphaPilot OS v2.7 多文件 FileOps 协议测试\n")
    
    tests = [
        test_parse_multi_file_protocol,
        test_single_file_fallback,
        test_empty_file_skip,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"\n❌ 测试失败: {test.__name__}")
            print(f"   错误: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    # 总结
    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    if failed == 0:
        print("\n🎉 所有测试通过! v2.7 多文件协议工作正常")
        return 0
    else:
        print(f"\n⚠️  {failed} 个测试失败,请检查代码")
        return 1


if __name__ == "__main__":
    exit(main())
