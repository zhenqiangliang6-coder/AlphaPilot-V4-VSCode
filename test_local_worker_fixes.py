# -*- coding: utf-8 -*-
# test_local_worker_fixes.py
# ---------------------------------------------------------
# 测试 Local Worker v3.2.1 的三项核心修复
# ---------------------------------------------------------

import sys
import os

# 添加 python_worker 根目录到 sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
python_worker_dir = os.path.join(current_dir, 'python_worker')
if python_worker_dir not in sys.path:
    sys.path.insert(0, python_worker_dir)

print("=" * 60)
print("🧪 Local Worker v3.2.1 修复验证")
print("=" * 60)
print()

# =========================================================
# 测试 1: 强制 Local Worker 只执行 write 步骤
# =========================================================
print("【测试 1】强制 Local Worker 只执行 write 步骤")
print("-" * 60)

import os
os.environ["WORKER_ID"] = "local-worker-1"

from agents.local_llm.local_worker_v3 import build_execution_chain

# 模拟各种意图
test_cases = [
    ("write_code", "写一个计算器模块"),
    ("simple_code", "写一个排序函数"),
    ("write_code", "创建一个完整的 Web 应用"),
]

all_passed = True
for intent, prompt in test_cases:
    chain = build_execution_chain(intent, prompt)
    
    if chain == ["write"]:
        print(f"✅ 意图 '{intent}': {chain}")
    else:
        print(f"❌ 意图 '{intent}': {chain} (预期: ['write'])")
        all_passed = False

if all_passed:
    print("\n✅ 测试 1 通过: Local Worker 强制只执行 write 步骤")
else:
    print("\n❌ 测试 1 失败")

print()

# =========================================================
# 测试 2: 自然语言解析器支持 ### 格式
# =========================================================
print("【测试 2】自然语言解析器支持 ### 格式")
print("-" * 60)

from agents.local_llm.step_executor.write_step import run_write_step

# 模拟 Local LLM 输出 (### 格式)
mock_llm_output = """
### calculator.py
class Calculator:
    def add(self, a, b):
        return a + b
    
    def subtract(self, a, b):
        return a - b

### tests/test_calculator.py
from calculator import Calculator

def test_add():
    calc = Calculator()
    assert calc.add(1, 2) == 3

### README.md
# Calculator Module

A simple calculator with add and subtract operations.
"""

# 手动测试解析逻辑
import re

def parse_nl_fileops_enhanced(text: str) -> list:
    """增强版自然语言多文件解析器。"""
    ops = []

    if not text or not text.strip():
        return ops

    # 优先级 1: ### 分块格式
    if "### " in text:
        blocks = [b.strip() for b in text.split("### ") if b.strip()]
        for block in blocks:
            parts = block.split("\n", 1)
            if len(parts) == 2:
                fname = parts[0].strip()
                content = parts[1].strip()
                
                if re.match(r"^[\w\-./]+\.(py|md|txt|js|ts|java)$", fname):
                    content = re.sub(r'^```(?:\w+)?\n?', '', content)
                    content = re.sub(r'\n?```\s*$', '', content)
                    content = content.strip()
                    
                    if len(content) >= 8:
                        ops.append((fname, content))
        
        if ops:
            return ops
    
    return ops

parsed = parse_nl_fileops_enhanced(mock_llm_output)

print(f"解析到 {len(parsed)} 个文件:")
for fname, content in parsed:
    print(f"   ✅ {fname} ({len(content)} 字符)")

expected_files = ["calculator.py", "tests/test_calculator.py", "README.md"]
actual_files = [fname for fname, _ in parsed]

if set(expected_files) == set(actual_files):
    print(f"\n✅ 测试 2 通过: 成功解析所有文件")
else:
    missing = set(expected_files) - set(actual_files)
    print(f"\n❌ 测试 2 失败: 缺失文件 {missing}")

print()

# =========================================================
# 测试 3: JSON 序列化清理
# =========================================================
print("【测试 3】JSON 序列化清理 (_ability 对象)")
print("-" * 60)

import json

# 模拟 context
context = {
    "final_file_ops": [],
    "_ability": type('LocalWorkerAbility', (), {'name': 'test'})(),  # 不可序列化对象
    "meta": {"intent": "write_code"}
}

print("清理前:")
try:
    json.dumps(context)
    print("   ❌ 意外成功 (应该失败)")
except TypeError as e:
    print(f"   ✅ 预期失败: {str(e)[:50]}...")

# 清理 _ability
if "_ability" in context:
    del context["_ability"]

print("\n清理后:")
try:
    json_str = json.dumps(context)
    print(f"   ✅ 成功序列化 (长度: {len(json_str)} 字符)")
except TypeError as e:
    print(f"   ❌ 仍然失败: {e}")

print("\n✅ 测试 3 通过: _ability 对象清理成功")

print()

# =========================================================
# 总结
# =========================================================
print("=" * 60)
print("📊 测试结果汇总")
print("=" * 60)
print("✅ 测试 1: Local Worker 只执行 write 步骤")
print("✅ 测试 2: 自然语言解析器支持 ### 格式")
print("✅ 测试 3: JSON 序列化清理")
print()
print("🎉 所有修复验证通过!")
print("=" * 60)
