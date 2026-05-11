# -*- coding: utf-8 -*-
# test_doubao_planner.py
"""
快速测试 Doubao Planner 是否正常工作
"""

import sys
sys.path.insert(0, '.')

from python_worker.agents.Volcengine.doubao_planner import llm_decompose_task

print("=" * 60)
print("测试 Doubao Planner")
print("=" * 60)

try:
    print("\n[1] 调用 Doubao Planner 拆解任务...")
    steps = llm_decompose_task("生成一个 Python 排序函数")
    
    print(f"\n✅ Planner 成功拆解 {len(steps)} 个步骤:")
    for i, step in enumerate(steps, 1):
        print(f"  Step {i}: {step['type']} (ID: {step['id']})")
    
    print("\n" + "=" * 60)
    print("测试通过！Doubao Planner 工作正常")
    print("=" * 60)
    
except Exception as e:
    print(f"\n❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()
    print("\n" + "=" * 60)
    print("使用降级策略测试...")
    print("=" * 60)
    
    # 测试降级策略
    from python_worker.agents.Volcengine.doubao_planner import _fallback_planner
    fallback_steps = _fallback_planner("生成一个排序函数", Exception("模拟错误"))
    print(f"\n✅ 降级策略生成 {len(fallback_steps)} 个步骤:")
    for i, step in enumerate(fallback_steps, 1):
        print(f"  Step {i}: {step['type']}")
