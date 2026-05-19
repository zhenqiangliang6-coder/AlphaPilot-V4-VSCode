# -*- coding: utf-8 -*-
"""
测试 Local Worker v3.0 FileOps 修复
验证 create_file_op(action="create") 是否能正确创建 FileOp
"""

import sys
import os

# 添加 python_worker 到路径
python_worker_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'python_worker'))
if python_worker_dir not in sys.path:
    sys.path.insert(0, python_worker_dir)

from file_ops import create_file_op, parse_fileops_v3
from python_worker.agents.local_llm.step_executor.write_step import parse_nl_fileops_enhanced

def test_create_file_op():
    """测试 create_file_op 参数修复"""
    print("=" * 60)
    print("测试 1: create_file_op 参数修复")
    print("=" * 60)
    
    try:
        # ✅ 正确的调用方式
        op = create_file_op(
            action="create",
            path="calculator.py",
            content="class Calculator:\n    pass"
        )
        print(f"✅ 成功创建 FileOp: {op['op']} - {op['path']}")
        print(f"   内容长度: {len(op['content'])} 字符\n")
        return True
    except Exception as e:
        print(f"❌ 创建失败: {e}\n")
        return False


def test_parse_and_create():
    """测试解析多文件并创建 FileOps"""
    print("=" * 60)
    print("测试 2: 解析 Gemma 4B 输出并创建 FileOps")
    print("=" * 60)
    
    # 模拟 Gemma 4B 的真实输出格式
    gemma_output = """### calculator.py
class Calculator:
    def add(self, a, b):
        return a + b

### tests/test_calculator.py
import unittest
from calculator import Calculator

class TestCalculator(unittest.TestCase):
    def test_add(self):
        calc = Calculator()
        self.assertEqual(calc.add(1, 2), 3)

### README.md
# Calculator Module
A simple calculator implementation.
"""
    
    print(f"输入文本长度: {len(gemma_output)} 字符\n")
    
    # 解析文件
    ops_raw = parse_nl_fileops_enhanced(gemma_output)
    print(f"✅ 解析到 {len(ops_raw)} 个文件:")
    for fname, content in ops_raw:
        print(f"   - {fname}: {len(content)} 字符")
    
    if not ops_raw:
        print("❌ 解析失败，返回空数组\n")
        return False
    
    print()
    
    # 创建 FileOps
    file_ops = []
    for fname, content in ops_raw:
        try:
            op = create_file_op(
                action="create",  # ⭐ 修复后的参数
                path=fname,
                content=content
            )
            file_ops.append(op)
            print(f"✅ 成功创建 FileOp: {op['op']} - {op['path']}")
        except Exception as e:
            print(f"❌ 创建 FileOp 失败 {fname}: {e}")
    
    print(f"\n📊 总结: 成功创建 {len(file_ops)}/{len(ops_raw)} 个 FileOp")
    
    if len(file_ops) == len(ops_raw):
        print("✅ 所有 FileOp 创建成功！\n")
        return True
    else:
        print("❌ 部分 FileOp 创建失败\n")
        return False


if __name__ == "__main__":
    print("\n🧪 Local Worker v3.0 FileOps 修复验证\n")
    
    test1_pass = test_create_file_op()
    test2_pass = test_parse_and_create()
    
    print("=" * 60)
    print("测试结果汇总:")
    print("=" * 60)
    print(f"测试 1 (create_file_op 参数): {'✅ 通过' if test1_pass else '❌ 失败'}")
    print(f"测试 2 (解析 + 创建 FileOps): {'✅ 通过' if test2_pass else '❌ 失败'}")
    print()
    
    if test1_pass and test2_pass:
        print("🎉 所有测试通过！Local Worker v3.0 FileOps 修复成功！")
    else:
        print("⚠️ 存在失败的测试，请检查代码")
    
    print("=" * 60 + "\n")
