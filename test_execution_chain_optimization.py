# -*- coding: utf-8 -*-
"""
测试 Local LLM Worker v3.0 执行链优化
验证简单任务是否使用简化链路
"""

import sys
import os

# 确保 python_worker 根目录在 sys.path 中
current_dir = os.path.dirname(os.path.abspath(__file__))
python_worker_dir = os.path.join(current_dir, 'python_worker')
if python_worker_dir not in sys.path:
    sys.path.insert(0, python_worker_dir)

from agents.local_llm.local_worker_v3 import build_execution_chain


def test_simple_task():
    """测试简单任务（应使用简化链路）"""
    print("=" * 60)
    print("🧪 测试 1: 简单任务 - '用python写一个排序函数'")
    print("=" * 60)
    
    prompt = "用python写一个排序函数"
    intent = "write_code"
    
    chain = build_execution_chain(intent, prompt)
    
    print(f"提示词长度: {len(prompt)}")
    print(f"意图: {intent}")
    print(f"执行链: {' → '.join(chain)}")
    print(f"步骤数: {len(chain)}")
    
    if len(chain) == 2 and chain == ["write", "test"]:
        print("✅ 通过：使用简化链路")
    else:
        print("❌ 失败：未使用简化链路")
    print()


def test_complex_task():
    """测试复杂任务（应使用完整链路）"""
    print("=" * 60)
    print("🧪 测试 2: 复杂任务 - '设计一个完整的用户认证系统...'")
    print("=" * 60)
    
    prompt = "设计一个完整的用户认证系统，包含JWT token、刷新机制、权限控制、数据库设计、API接口、单元测试和文档"
    intent = "write_code"
    
    chain = build_execution_chain(intent, prompt)
    
    print(f"提示词长度: {len(prompt)}")
    print(f"意图: {intent}")
    print(f"执行链: {' → '.join(chain)}")
    print(f"步骤数: {len(chain)}")
    
    if len(chain) >= 6:
        print("✅ 通过：使用完整链路")
    else:
        print("❌ 失败：错误地使用了简化链路")
    print()


def test_other_intent():
    """测试其他意图（应保持原样）"""
    print("=" * 60)
    print("🧪 测试 3: 其他意图 - 'chat'")
    print("=" * 60)
    
    prompt = "你好"
    intent = "chat"
    
    chain = build_execution_chain(intent, prompt)
    
    print(f"提示词长度: {len(prompt)}")
    print(f"意图: {intent}")
    print(f"执行链: {' → '.join(chain)}")
    print(f"步骤数: {len(chain)}")
    
    if chain == ["analyze", "write"]:
        print("✅ 通过：保持原有链路")
    else:
        print("❌ 失败：链路被错误修改")
    print()


if __name__ == "__main__":
    print("\n🚀 开始测试 Local LLM Worker v3.0 执行链优化\n")
    
    test_simple_task()
    test_complex_task()
    test_other_intent()
    
    print("=" * 60)
    print("✅ 所有测试完成！")
    print("=" * 60)
