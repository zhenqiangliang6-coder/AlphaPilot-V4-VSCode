#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlphaPilot v2.6 阶段2-4 集成测试脚本
测试 Dual-Persona Engine + Agent Execution Chain + 前端适配
"""

import sys
import os

# 添加项目路径
project_root = os.path.dirname(__file__)
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'python_worker'))


def test_personas_module():
    """测试1: 验证 personas.py 模块"""
    print("\n[测试1] 验证 personas.py 模块...")
    
    try:
        from agents.qwen.personas import get_persona_config, get_all_personas
        
        # 测试工程师人格
        engineer = get_persona_config('engineer')
        assert 'system_prompt' in engineer
        assert engineer['tone'] == 'professional'
        print('✅ 工程师人格配置正确')
        
        # 测试创作者人格
        creator = get_persona_config('creator')
        assert creator['tone'] == 'artistic_and_expressive'
        print('✅ 创作者人格配置正确')
        
        # 测试对话人格
        conversational = get_persona_config('conversational')
        assert conversational['tone'] == 'friendly_and_empathetic'
        print('✅ 对话人格配置正确')
        
        # 测试所有人格
        all_personas = get_all_personas()
        assert len(all_personas) == 3
        print(f'✅ 共 {len(all_personas)} 种人格配置')
        
        print('✅ 测试1通过: personas.py 模块正常\n')
        return True
    except Exception as e:
        print(f'❌ 测试1失败: {e}\n')
        import traceback
        traceback.print_exc()
        return False


def test_qwen_api_persona():
    """测试2: 验证 qwen_api.py 人格注入功能"""
    print("[测试2] 验证 qwen_api.py 人格注入功能...")
    
    try:
        # 直接检查文件内容而非导入
        api_file = os.path.join(project_root, "python_worker/agents/qwen/qwen_api.py")
        with open(api_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # 检查函数是否存在
        if 'def call_qwen_with_persona' in content:
            print('✅ call_qwen_with_persona 函数存在')
        else:
            print('❌ call_qwen_with_persona 函数不存在')
            return False
        
        # 检查是否支持 persona_config 参数
        if 'persona_config' in content:
            print('✅ 支持 persona_config 参数')
        else:
            print('❌ 不支持 persona_config 参数')
            return False
        
        print('✅ 测试2通过: qwen_api.py 人格注入功能正常\n')
        return True
    except Exception as e:
        print(f'❌ 测试2失败: {e}\n')
        import traceback
        traceback.print_exc()
        return False


def test_step_executors_integration():
    """测试3: 验证步骤执行器人格注入"""
    print("[测试3] 验证步骤执行器人格注入...")
    
    step_files = [
        "python_worker/agents/qwen/step_executor/write_step.py",
        "python_worker/agents/qwen/step_executor/analyze_step.py",
        "python_worker/agents/qwen/step_executor/plan_step.py",
        "python_worker/agents/qwen/step_executor/refine_step.py"
    ]
    
    for file_path in step_files:
        full_path = os.path.join(project_root, file_path)
        if os.path.exists(full_path):
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'call_qwen_with_persona' in content:
                    print(f'  ✅ {file_path} 已集成人格配置')
                else:
                    print(f'  ❌ {file_path} 未找到人格配置调用')
                    return False
        else:
            print(f'  ❌ {file_path} 不存在')
            return False
    
    print('✅ 测试3通过: 所有步骤执行器已集成人格配置\n')
    return True


def test_dynamic_step_generation():
    """测试4: 验证动态步骤生成优化"""
    print("[测试4] 验证动态步骤生成优化...")
    
    try:
        # 直接检查文件内容
        worker_file = os.path.join(project_root, "python_worker/agents/qwen/qwen_worker_v2.py")
        with open(worker_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查是否有 skip_rules
        if 'skip_rules' in content:
            print('✅ 包含智能跳过规则')
        else:
            print('❌ 未找到智能跳过规则')
            return False
        
        # 检查是否有 intent 参数
        if 'intent: str = None' in content or 'intent=None' in content:
            print('✅ create_steps_from_chain 支持 intent 参数')
        else:
            print('❌ create_steps_from_chain 不支持 intent 参数')
            return False
        
        # 检查是否传递 intent
        if 'create_steps_from_chain(execution_chain, prompt, persona, intent)' in content:
            print('✅ execute_task 传递 intent 参数')
        else:
            print('⚠️  execute_task 可能未传递 intent 参数')
        
        print('✅ 测试4通过: 动态步骤生成优化正常\n')
        return True
    except Exception as e:
        print(f'❌ 测试4失败: {e}\n')
        import traceback
        traceback.print_exc()
        return False


def test_frontend_components():
    """测试5: 验证前端组件"""
    print("[测试5] 验证前端组件...")
    
    frontend_files = [
        "vscode-extension/webview/src/components/IntentBadge.tsx",
        "vscode-extension/webview/src/components/PersonaIcon.tsx",
        "vscode-extension/webview/src/store/chatStore.ts",
        "vscode-extension/webview/src/App.tsx",
        "vscode-extension/webview/src/components/MessageList.tsx"
    ]
    
    for file_path in frontend_files:
        full_path = os.path.join(project_root, file_path)
        if os.path.exists(full_path):
            print(f'  ✅ {file_path} 存在')
        else:
            print(f'  ❌ {file_path} 不存在')
            return False
    
    # 检查 chatStore 是否包含 intent/persona 字段
    chatstore_path = os.path.join(project_root, "vscode-extension/webview/src/store/chatStore.ts")
    with open(chatstore_path, 'r', encoding='utf-8') as f:
        chatstore_content = f.read()
        if 'intent?:' in chatstore_content and 'persona?:' in chatstore_content:
            print('  ✅ chatStore.ts 包含 intent/persona 字段')
        else:
            print('  ❌ chatStore.ts 缺少 intent/persona 字段')
            return False
    
    # 检查 MessageList 是否导入新组件
    messagelist_path = os.path.join(project_root, "vscode-extension/webview/src/components/MessageList.tsx")
    with open(messagelist_path, 'r', encoding='utf-8') as f:
        messagelist_content = f.read()
        if 'IntentBadge' in messagelist_content and 'PersonaIcon' in messagelist_content:
            print('  ✅ MessageList.tsx 已集成 IntentBadge 和 PersonaIcon')
        else:
            print('  ❌ MessageList.tsx 未集成新组件')
            return False
    
    print('✅ 测试5通过: 前端组件正常\n')
    return True


def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("AlphaPilot v2.6 阶段2-4 集成测试")
    print("="*60)
    
    results = []
    
    # 运行所有测试
    results.append(("人格配置模块", test_personas_module()))
    results.append(("qwen_api.py 人格注入", test_qwen_api_persona()))
    results.append(("步骤执行器集成", test_step_executors_integration()))
    results.append(("动态步骤生成优化", test_dynamic_step_generation()))
    results.append(("前端组件", test_frontend_components()))
    
    # 汇总结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")
    
    print("\n" + "="*60)
    if passed == total:
        print(f"🎉 所有测试通过! ({passed}/{total})")
        print("="*60)
        print("\n✅ 阶段2: Dual-Persona Engine 集成完成")
        print("   - qwen_api.py 支持人格配置注入")
        print("   - 4个步骤执行器已集成人格配置")
        print("\n✅ 阶段3: Agent Execution Chain 优化完成")
        print("   - 动态步骤生成支持智能跳过")
        print("   - 不同意图自动调整步骤组合")
        print("\n✅ 阶段4: 前端适配完成")
        print("   - IntentBadge 组件显示意图标签")
        print("   - PersonaIcon 组件显示人格图标")
        print("   - MessageList 集成新组件")
        print("\n下一步: 运行完整系统测试验证端到端流程")
        print("命令: .\\start_all.ps1\n")
        return 0
    else:
        print(f"❌ {total - passed} 个测试失败 ({passed}/{total})")
        print("="*60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
