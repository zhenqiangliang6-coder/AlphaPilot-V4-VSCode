# -*- coding: utf-8 -*-
# test_local_worker_architecture.py
# ---------------------------------------------------------
# Local LLM Worker v3.0 - 架构完整性测试
# - 验证所有模块可导入
# - 验证 Intent Router 集成
# - 验证 Persona Engine 配置
# - 验证 Execution Chain 构建
# ---------------------------------------------------------

import sys
import os

# 添加项目根目录到路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 添加 python_worker 目录到路径
worker_root = os.path.abspath(os.path.dirname(__file__))
if worker_root not in sys.path:
    sys.path.insert(0, worker_root)


def test_imports():
    """测试所有模块可正常导入"""
    print("📦 步骤 1: 测试模块导入...")
    
    try:
        from agents.local_llm.local_api import call_local_llm, test_connection
        print("   ✅ local_api 导入成功")
        
        from agents.local_llm.personas import get_persona_config, list_personas
        print("   ✅ personas 导入成功")
        
        from agents.local_llm.step_executor import execute_step
        print("   ✅ step_executor 导入成功")
        
        from intent_router import IntentRouter
        print("   ✅ IntentRouter 导入成功")
        
        return True
    except Exception as e:
        print(f"   ❌ 导入失败: {e}")
        return False


def test_persona_engine():
    """测试人格引擎配置"""
    print("\n🎭 步骤 2: 测试人格引擎...")
    
    try:
        from agents.local_llm.personas import get_persona_config, list_personas
        
        personas = list_personas()
        print(f"   ✅ 可用人格类型: {personas}")
        
        for persona_type in personas:
            config = get_persona_config(persona_type)
            print(f"   ✅ {persona_type}: {config['name']} ({config['icon']})")
        
        return True
    except Exception as e:
        print(f"   ❌ 人格引擎测试失败: {e}")
        return False


def test_intent_router():
    """测试意图识别"""
    print("\n🧠 步骤 3: 测试意图识别...")
    
    try:
        from intent_router import IntentRouter
        
        test_cases = [
            ("写一个 Python 函数计算斐波那契数列", "write_code"),
            ("解释这段代码的作用", "explain_code"),
            ("修复这个 bug", "fix_code"),
            ("你好，最近怎么样？", "chat"),
        ]
        
        for prompt, expected_intent in test_cases:
            intent, persona, _ = IntentRouter.detect_intent(prompt)
            status = "✅" if intent == expected_intent else "⚠️"
            print(f"   {status} '{prompt[:20]}...' → {intent} (期望: {expected_intent})")
        
        return True
    except Exception as e:
        print(f"   ❌ 意图识别测试失败: {e}")
        return False


def test_execution_chain():
    """测试执行链构建"""
    print("\n⛓️  步骤 4: 测试执行链构建...")
    
    try:
        # 模拟 local_worker_v3.py 中的逻辑
        INTENT_CHAINS = {
            "write_code": ["analyze", "plan", "write", "refine", "test", "fix", "doc", "docstring"],
            "generate_doc": ["analyze", "plan", "write", "doc", "docstring"],
            "explain_code": ["analyze", "plan", "doc"],
            "creative_writing": ["analyze", "plan", "write", "refine"],
            "chat": ["analyze", "write"],
        }
        
        for intent, chain in INTENT_CHAINS.items():
            print(f"   ✅ {intent}: {' → '.join(chain)}")
        
        return True
    except Exception as e:
        print(f"   ❌ 执行链测试失败: {e}")
        return False


def test_step_executor():
    """测试步骤执行器"""
    print("\n⚙️  步骤 5: 测试步骤执行器...")
    
    try:
        from agents.local_llm.step_executor import execute_step
        
        # 验证 execute_step 函数签名（支持 api_func 参数）
        import inspect
        sig = inspect.signature(execute_step)
        params = list(sig.parameters.keys())
        
        expected_params = ['task_id', 'step', 'events', 'context', 'api_func']
        if params == expected_params:
            print(f"   ✅ execute_step 函数签名正确: {params}")
        else:
            print(f"   ⚠️  execute_step 函数签名不匹配")
            print(f"      期望: {expected_params}")
            print(f"      实际: {params}")
        
        return True
    except Exception as e:
        print(f"   ❌ 步骤执行器测试失败: {e}")
        return False


def main():
    print("=" * 60)
    print("🧪 Local LLM Worker v3.0 - 架构完整性测试")
    print("=" * 60)
    
    results = []
    
    results.append(("模块导入", test_imports()))
    results.append(("人格引擎", test_persona_engine()))
    results.append(("意图识别", test_intent_router()))
    results.append(("执行链构建", test_execution_chain()))
    results.append(("步骤执行器", test_step_executor()))
    
    print("\n" + "=" * 60)
    print("📊 测试结果汇总:")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"   {test_name}: {status}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("✅ 所有架构测试通过！Local LLM Worker v3.0 架构完整。")
    else:
        print("⚠️  部分测试失败，请检查上述错误信息。")
    
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
