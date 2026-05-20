# -*- coding: utf-8 -*-
"""
测试 Local Worker v3.2.3 ASCII 文件树功能
验证 Gemma 4B 能否正确输出并解析 ASCII 文件树
"""

import sys
import os

# 添加 python_worker 到路径
python_worker_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'python_worker'))
if python_worker_dir not in sys.path:
    sys.path.insert(0, python_worker_dir)

from python_worker.agents.local_llm.step_executor.write_step import extract_ascii_tree
from python_worker.agents.local_llm.step_executor.prompts import write_prompt


def test_extract_ascii_tree():
    """测试 ASCII 文件树提取功能"""
    print("=" * 60)
    print("测试 1: extract_ascii_tree 函数")
    print("=" * 60)
    
    # 模拟 Gemma 4B 的输出（包含 ### FILE_TREE）
    gemma_output = """### calculator.py
class Calculator:
    def add(self, a, b):
        return a + b

### tests/test_calculator.py
def test_add():
    assert calc.add(1, 2) == 3

### README.md
# Calculator Module

### FILE_TREE
project/
├── calculator.py
├── tests/
│   └── test_calculator.py
└── README.md
"""
    
    print(f"输入文本长度: {len(gemma_output)} 字符\n")
    
    # 提取 ASCII 树
    ascii_tree = extract_ascii_tree(gemma_output)
    
    if ascii_tree:
        print(f"✅ 成功提取 ASCII 文件树:")
        print(ascii_tree)
        print()
        
        # 验证内容
        expected_files = ["calculator.py", "test_calculator.py", "README.md"]
        for file in expected_files:
            if file in ascii_tree:
                print(f"✅ 找到文件: {file}")
            else:
                print(f"❌ 未找到文件: {file}")
        
        return True
    else:
        print("❌ 提取失败，返回空字符串\n")
        return False


def test_write_prompt_includes_file_tree():
    """测试 write_prompt 是否包含 ASCII 文件树要求"""
    print("\n" + "=" * 60)
    print("测试 2: write_prompt 包含 ASCII 文件树要求")
    print("=" * 60)
    
    plan = "生成一个简单的计算器模块"
    prompt = write_prompt(plan)
    
    # 检查 prompt 是否包含 ASCII 文件树相关要求
    checks = [
        ("FILE_TREE", "FILE_TREE" in prompt),
        ("ASCII 文件树", "ASCII 文件树" in prompt),
        ("├─", "├─" in prompt or "├──" in prompt),
        ("文件夹后面加 /", "文件夹后面加 /" in prompt),
    ]
    
    all_pass = True
    for check_name, result in checks:
        status = "✅" if result else "❌"
        print(f"{status} {check_name}: {'包含' if result else '缺失'}")
        if not result:
            all_pass = False
    
    if all_pass:
        print("\n✅ write_prompt 已正确包含 ASCII 文件树要求")
        return True
    else:
        print("\n❌ write_prompt 缺少部分要求")
        return False


def test_no_file_tree():
    """测试当 LLM 未输出文件树时的行为"""
    print("\n" + "=" * 60)
    print("测试 3: 无 ASCII 文件树的情况")
    print("=" * 60)
    
    # 模拟没有 ### FILE_TREE 的输出
    gemma_output_no_tree = """### calculator.py
class Calculator:
    pass
"""
    
    print("输入文本（无 FILE_TREE）:\n", gemma_output_no_tree)
    
    ascii_tree = extract_ascii_tree(gemma_output_no_tree)
    
    if ascii_tree == "":
        print("\n✅ 正确处理：返回空字符串（不报错）")
        return True
    else:
        print(f"\n❌ 错误处理：返回了非空字符串: {ascii_tree}")
        return False


if __name__ == "__main__":
    print("\n🧪 Local Worker v3.2.3 ASCII 文件树功能验证\n")
    
    test1_pass = test_extract_ascii_tree()
    test2_pass = test_write_prompt_includes_file_tree()
    test3_pass = test_no_file_tree()
    
    print("\n" + "=" * 60)
    print("测试结果汇总:")
    print("=" * 60)
    print(f"测试 1 (extract_ascii_tree): {'✅ 通过' if test1_pass else '❌ 失败'}")
    print(f"测试 2 (write_prompt 包含要求): {'✅ 通过' if test2_pass else '❌ 失败'}")
    print(f"测试 3 (无文件树容错): {'✅ 通过' if test3_pass else '❌ 失败'}")
    print()
    
    if test1_pass and test2_pass and test3_pass:
        print("🎉 所有测试通过！Local Worker v3.2.3 ASCII 文件树功能就绪！")
    else:
        print("️ 存在失败的测试，请检查代码")
    
    print("=" * 60 + "\n")
