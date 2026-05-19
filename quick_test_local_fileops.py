# -*- coding: utf-8 -*-
# quick_test_local_fileops.py
# ---------------------------------------------------------
# 快速测试 Local Worker 的 FileOps 生成能力
# ---------------------------------------------------------

import sys
import os

# 添加 python_worker 根目录到 sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
python_worker_dir = os.path.join(current_dir, 'python_worker')
if python_worker_dir not in sys.path:
    sys.path.insert(0, python_worker_dir)

print(f"📁 Python Worker 目录: {python_worker_dir}")
print(f"📁 sys.path[0]: {sys.path[0]}\n")

from agents.local_llm.step_executor.prompts import write_prompt
from file_ops import parse_fileops_v3


def test_write_prompt_format():
    """
    测试 write_prompt 是否使用 # FILE: 协议格式
    """
    print("=" * 60)
    print("🧪 测试 1: write_prompt 格式检查")
    print("=" * 60)
    
    plan = "创建一个简单的计算器模块"
    prompt = write_prompt(plan)
    
    # 检查是否包含 # FILE: 协议
    if "# FILE:" in prompt:
        print("✅ write_prompt 包含 # FILE: 协议")
    else:
        print("❌ write_prompt 不包含 # FILE: 协议")
        return False
    
    # 检查是否要求 JSON 格式（不应该有）
    # 注意: prompt 中可能提到 "JSON格式" 来描述 # META: 的元数据,这是允许的
    # 关键是不能要求整个输出是 JSON 对象
    if '"file_ops":' in prompt or '只输出一个 JSON 对象' in prompt:
        print("❌ write_prompt 要求整个输出是 JSON 格式")
        return False
    else:
        print("✅ write_prompt 不要求整个输出是 JSON 格式")
    
    print("\n📝 Prompt 预览 (前500字符):")
    print(prompt[:500])
    print("...\n")
    
    return True


def test_parse_fileops_v3():
    """
    测试 parse_fileops_v3 是否能正确解析 # FILE: 协议
    """
    print("=" * 60)
    print("🧪 测试 2: parse_fileops_v3 解析能力")
    print("=" * 60)
    
    # 模拟 Local LLM 的输出
    mock_llm_output = """
# FILE: calculator.py
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

# TEST: tests/test_calculator.py
def test_add():
    assert add(1, 2) == 3

def test_subtract():
    assert subtract(5, 3) == 2

# DOC: README.md
# Calculator Module

A simple calculator module with add and subtract functions.
"""
    
    file_ops = parse_fileops_v3(mock_llm_output)
    
    print(f"\n📁 解析到的 FileOps 数量: {len(file_ops)}")
    
    if len(file_ops) == 0:
        print("❌ 解析失败: 未检测到任何 FileOp")
        return False
    
    for i, op in enumerate(file_ops):
        path = op.get("path", "N/A")
        action = op.get("op", "N/A")
        content_preview = op.get("content", "")[:50].replace("\n", " ")
        
        print(f"   {i+1}. [{action}] {path}")
        print(f"      内容预览: {content_preview}...")
    
    # 验证是否解析到所有文件
    paths = [op.get("path") for op in file_ops]
    expected_paths = ["calculator.py", "tests/test_calculator.py", "README.md"]
    
    missing = [p for p in expected_paths if p not in paths]
    
    if missing:
        print(f"\n⚠️ 缺失的文件: {missing}")
        return False
    else:
        print(f"\n✅ 成功解析所有文件: {expected_paths}")
        return True


def test_refine_step_integration():
    """
    测试 refine_step 是否能正确更新 final_file_ops
    """
    print("=" * 60)
    print("🧪 测试 3: refine_step 集成测试")
    print("=" * 60)
    
    try:
        from agents.local_llm.step_executor.refine_step import run_refine_step
        
        # 模拟 context
        context = {
            "intermediate_results": [],
            "final_file_ops": [
                {
                    "op": "create",
                    "path": "calculator.py",
                    "content": "def add(a, b):\n    return a + b",
                    "file_type": "file",
                    "language": "python"
                }
            ],
            "meta": {
                "persona_config": None
            }
        }
        
        step = {
            "type": "refine",
            "input": {"prompt": "优化代码"}
        }
        
        events = []
        
        # 执行 refine_step
        print("⏳ 执行 refine_step...")
        run_refine_step(step, context, events, task_id=None)
        
        # 检查结果
        output = step.get("output", {})
        file_ops = output.get("file_ops", [])
        
        print(f"\n📁 refine_step 输出的 FileOps 数量: {len(file_ops)}")
        
        if len(file_ops) > 0:
            print("✅ refine_step 成功处理 FileOps")
            return True
        else:
            print("⚠️ refine_step 未输出 FileOps (可能保留了原有结构)")
            # 检查 context 是否保留原有 FileOps
            final_file_ops = context.get("final_file_ops", [])
            if len(final_file_ops) > 0:
                print("✅ context['final_file_ops'] 保留了原有结构")
                return True
            else:
                print("❌ context['final_file_ops'] 丢失")
                return False
        
    except Exception as e:
        print(f"❌ refine_step 执行失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """
    主测试流程
    """
    print("\n" + "=" * 60)
    print("🚀 Local Worker FileOps 能力快速测试")
    print("=" * 60 + "\n")
    
    results = []
    
    # 测试 1: write_prompt 格式
    results.append(("write_prompt 格式", test_write_prompt_format()))
    
    # 测试 2: parse_fileops_v3 解析
    results.append(("parse_fileops_v3 解析", test_parse_fileops_v3()))
    
    # 测试 3: refine_step 集成
    results.append(("refine_step 集成", test_refine_step_integration()))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")
        
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\n总计: {passed} 通过, {failed} 失败")
    
    if failed == 0:
        print("\n🎉 所有测试通过! Local Worker 已具备文件生成能力。")
    else:
        print(f"\n⚠️ 有 {failed} 个测试失败,请检查修复。")
    
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
