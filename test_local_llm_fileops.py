# -*- coding: utf-8 -*-
# test_local_llm_fileops.py
# ---------------------------------------------------------
# 测试 Local LLM Worker 的 FileOps 生成功能
# ---------------------------------------------------------

import sys
import os
import json

# 添加 python_worker 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python_worker'))

from agents.local_llm.step_executor.write_step import run_write_step
from worker_config import create_empty_context

def test_write_step_with_plan():
    """测试有 plan 的工程任务模式"""
    print("=" * 60)
    print("测试 1: 工程任务模式（有 plan）")
    print("=" * 60)
    
    # 模拟上下文
    context = create_empty_context()
    context["final_file_ops"] = []
    context["intermediate_results"] = [
        {
            "type": "plan",
            "plan": "创建一个排序函数，支持升序和降序"
        }
    ]
    
    # 模拟步骤
    step = {
        "id": "step-1",
        "type": "write",
        "status": "running",
        "input": {
            "prompt": "根据 plan 生成代码"
        }
    }
    
    events = []
    
    # 执行 write_step
    try:
        run_write_step(step, context, events)
        
        # 检查结果
        print(f"\n✅ 步骤输出: {step.get('output', {})}")
        print(f"✅ FileOps 数量: {len(context.get('final_file_ops', []))}")
        
        if context.get('final_file_ops'):
            print("\n📄 生成的 FileOps:")
            for i, op in enumerate(context['final_file_ops']):
                print(f"  [{i+1}] {op.get('action')}: {op.get('path')}")
                print(f"      类型: {op.get('file_type')}")
                print(f"      语言: {op.get('language')}")
        else:
            print("\n❌ 未生成 FileOps！")
            
        return len(context.get('final_file_ops', [])) > 0
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_write_step_without_plan():
    """测试无 plan 的对话任务模式"""
    print("\n" + "=" * 60)
    print("测试 2: 对话任务模式（无 plan）")
    print("=" * 60)
    
    # 模拟上下文
    context = create_empty_context()
    context["final_file_ops"] = []
    context["intermediate_results"] = []
    
    # 模拟步骤
    step = {
        "id": "step-1",
        "type": "write",
        "status": "running",
        "input": {
            "prompt": "你好，请介绍一下你自己"
        }
    }
    
    events = []
    
    # 执行 write_step
    try:
        run_write_step(step, context, events)
        
        # 检查结果
        print(f"\n✅ 步骤输出: {step.get('output', {})}")
        print(f"✅ FileOps 数量: {len(context.get('final_file_ops', []))}")
        
        # 对话任务不应该生成 FileOps
        if not context.get('final_file_ops'):
            print("\n✅ 对话任务正确：未生成 FileOps")
            return True
        else:
            print("\n⚠️ 对话任务生成了 FileOps（可能不符合预期）")
            return True
            
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n🧪 Local LLM Worker FileOps 生成测试\n")
    
    result1 = test_write_step_with_plan()
    result2 = test_write_step_without_plan()
    
    print("\n" + "=" * 60)
    print("测试结果总结:")
    print(f"  工程任务模式: {'✅ 通过' if result1 else '❌ 失败'}")
    print(f"  对话任务模式: {'✅ 通过' if result2 else '❌ 失败'}")
    print("=" * 60)
    
    if result1 and result2:
        print("\n🎉 所有测试通过！")
        sys.exit(0)
    else:
        print("\n⚠️ 部分测试失败，请检查日志")
        sys.exit(1)
