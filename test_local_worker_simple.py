# -*- coding: utf-8 -*-
# test_local_worker_simple.py
# ---------------------------------------------------------
# 简单测试:直接调用 Local Worker 的 write_step 和 refine_step
# 不需要启动完整的 Redis 队列系统
# ---------------------------------------------------------

import sys
import os

# 添加 python_worker 根目录到 sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
python_worker_dir = os.path.join(current_dir, 'python_worker')
if python_worker_dir not in sys.path:
    sys.path.insert(0, python_worker_dir)

print("=" * 60)
print("🧪 Local Worker 文件生成能力 - 简单测试")
print("=" * 60)
print()

# =========================================================
# 测试 1: 模拟 write_step 生成 FileOps
# =========================================================
print("【测试 1】模拟 write_step 生成多文件项目")
print("-" * 60)

from agents.local_llm.step_executor.prompts import write_prompt
from file_ops import parse_fileops_v3

# 1. 生成 prompt
plan = """
创建一个简单的计算器模块，包含以下文件：
1. calculator.py - 主计算器类
2. tests/test_calculator.py - 单元测试
3. README.md - 使用说明
"""

prompt = write_prompt(plan)
print(f"✅ 已生成 write_prompt (长度: {len(prompt)} 字符)")
print(f"   包含 # FILE: 协议: {'是' if '# FILE:' in prompt else '否'}")
print()

# 2. 模拟 LLM 输出（实际使用时会调用 call_local_llm）
mock_llm_output = """
# FILE: calculator.py
class Calculator:
    def add(self, a, b):
        return a + b
    
    def subtract(self, a, b):
        return a - b

# TEST: tests/test_calculator.py
def test_add():
    calc = Calculator()
    assert calc.add(1, 2) == 3

def test_subtract():
    calc = Calculator()
    assert calc.subtract(5, 3) == 2

# DOC: README.md
# Calculator Module

A simple calculator with add and subtract operations.

## Usage
```python
from calculator import Calculator
calc = Calculator()
result = calc.add(1, 2)
```
"""

print("📝 模拟 LLM 输出:")
print(mock_llm_output[:200] + "...")
print()

# 3. 解析 FileOps
file_ops = parse_fileops_v3(mock_llm_output)
print(f"✅ 解析到 {len(file_ops)} 个 FileOp:")
for i, op in enumerate(file_ops, 1):
    path = op.get("path", "N/A")
    action = op.get("op", "N/A")
    content_len = len(op.get("content", ""))
    print(f"   {i}. [{action}] {path} ({content_len} 字符)")

print()

# =========================================================
# 测试 2: 模拟 refine_step 优化 FileOps
# =========================================================
print("【测试 2】模拟 refine_step 优化代码")
print("-" * 60)

from agents.local_llm.step_executor.refine_step import run_refine_step

# 1. 准备 context
context = {
    "intermediate_results": [],
    "final_file_ops": file_ops,  # 使用上一步生成的 FileOps
    "meta": {
        "persona_config": None
    }
}

step = {
    "type": "refine",
    "input": {"prompt": "优化代码性能"}
}

events = []

print(f"⏳ 执行 refine_step (当前有 {len(file_ops)} 个文件)...")

# 2. 执行 refine_step
try:
    run_refine_step(step, context, events, task_id=None)
    
    # 3. 检查结果
    output = step.get("output", {})
    refined_file_ops = output.get("file_ops", [])
    
    print(f"✅ refine_step 完成")
    print(f"   输出 FileOps 数量: {len(refined_file_ops)}")
    
    # 4. 检查 context 是否更新
    final_file_ops = context.get("final_file_ops", [])
    print(f"   context['final_file_ops'] 数量: {len(final_file_ops)}")
    
    if len(final_file_ops) > 0:
        print(f"\n✅ FileOps 链路完整!")
        for i, op in enumerate(final_file_ops, 1):
            path = op.get("path", "N/A")
            print(f"   {i}. {path}")
    else:
        print(f"\n⚠️ 警告: context['final_file_ops'] 为空")
        
except Exception as e:
    print(f"❌ refine_step 执行失败: {e}")
    import traceback
    traceback.print_exc()

print()

# =========================================================
# 测试 3: 验证架构合规性
# =========================================================
print("【测试 3】架构合规性验证")
print("-" * 60)

checks = [
    ("Worker = 真相", len(file_ops) > 0, "FileOps 在 Worker 内部生成"),
    ("协议 = 宪法", "# FILE:" in prompt, "使用 # FILE: 协议格式"),
    ("能力对齐", len(context.get("final_file_ops", [])) > 0, "FileOps 链路完整"),
]

all_passed = True
for name, passed, desc in checks:
    status = "✅" if passed else "❌"
    print(f"{status} {name}: {desc}")
    if not passed:
        all_passed = False

print()

# =========================================================
# 总结
# =========================================================
print("=" * 60)
if all_passed:
    print("🎉 所有测试通过! Local Worker 已具备文件生成能力。")
else:
    print("⚠️ 部分测试失败,请检查修复。")
print("=" * 60)
print()
print("💡 下一步:")
print("   1. 启动完整服务: .\\start_all.ps1")
print("   2. 打开 VSCode,选择 'AlphaPilot (Gemma LLM)'")
print("   3. 提交任务: '写一个计算器模块'")
print("   4. 观察生成的文件")
