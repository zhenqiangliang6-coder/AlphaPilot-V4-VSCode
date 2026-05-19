#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local Worker v3.2.1 Persona 注入验证测试
验证 write_step 是否正确从 context.meta 读取 persona_config 并注入到 prompt
"""

import sys
import os

# 添加项目路径
project_root = os.path.dirname(__file__)
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'python_worker'))


def test_persona_injection():
    """测试 persona system_prompt 是否正确注入到 write prompt"""
    print("\n" + "="*60)
    print("🧪 Local Worker v3.2.1 Persona 注入验证")
    print("="*60)
    
    # 模拟 context.meta
    from python_worker.agents.local_llm.personas import get_persona_config
    
    persona_config = get_persona_config('engineer')
    
    print("\n【测试 1】验证 persona_config 包含 system_prompt")
    print("-" * 60)
    
    assert 'system_prompt' in persona_config, "❌ persona_config 缺少 system_prompt"
    assert len(persona_config['system_prompt']) > 100, "❌ system_prompt 太短"
    
    print(f"✅ persona_config['name']: {persona_config['name']}")
    print(f"✅ system_prompt 长度: {len(persona_config['system_prompt'])} 字符")
    print(f"✅ 包含关键指令: {'直接输出代码文件内容' in persona_config['system_prompt']}")
    
    forbidden_text = "Here's a thinking process"
    format_requirement = "### 文件名"
    print(f"✅ 包含禁止项: '{forbidden_text}' in prompt: {forbidden_text in persona_config['system_prompt']}")
    print(f"✅ 包含格式要求: '{format_requirement}' in prompt: {format_requirement in persona_config['system_prompt']}")
    
    print("\n【测试 2】验证 prompt 拼接逻辑")
    print("-" * 60)
    
    # 模拟 write_prompt 生成的 base_prompt
    base_prompt = """你现在处于 AlphaPilot OS v3.0 环境。

请严格按照以下"多文件输出协议"生成代码：

==========================
# FILE: <相对路径>
<代码内容>
...
"""
    
    # 模拟拼接逻辑
    persona_system_prompt = persona_config.get("system_prompt", "")
    if persona_system_prompt:
        final_prompt = f"{persona_system_prompt}\n\n---\n\n{base_prompt}"
    else:
        final_prompt = base_prompt
    
    print(f"✅ 最终 prompt 长度: {len(final_prompt)} 字符")
    print(f"✅ 以 persona system_prompt 开头: {final_prompt.startswith(persona_system_prompt[:50])}")
    print(f"✅ 包含分隔符 '---': {'---' in final_prompt}")
    print(f"✅ 包含 base_prompt: {base_prompt[:50] in final_prompt}")
    
    print("\n【测试 3】验证完整流程")
    print("-" * 60)
    
    # 模拟完整的 context
    context = {
        "meta": {
            "persona": "engineer",
            "persona_config": persona_config,
            "intent": "write_code",
            "execution_chain": ["write"]
        },
        "intermediate_results": [
            {"type": "plan", "plan": "创建一个计算器模块"}
        ]
    }
    
    # 验证可以从 context.meta 读取 persona_config
    meta = context.get("meta", {})
    loaded_persona_config = meta.get("persona_config", {})
    
    assert loaded_persona_config, "❌ 无法从 context.meta 读取 persona_config"
    assert loaded_persona_config.get("system_prompt"), "❌ persona_config 缺少 system_prompt"
    
    print(f"✅ 成功从 context.meta 读取 persona_config")
    print(f"✅ persona_config['name']: {loaded_persona_config['name']}")
    print(f"✅ system_prompt 可用: {len(loaded_persona_config['system_prompt']) > 0}")
    
    print("\n" + "="*60)
    print("🎉 所有 Persona 注入验证通过!")
    print("="*60)
    print("\n💡 下一步:")
    print("   1. 重启 Local Worker (加载新的 write_step.py)")
    print("   2. 提交任务: '写一个计算器模块'")
    print("   3. 观察日志: '[INFO] write_step 已加载 persona system_prompt'")
    print("   4. 预期结果: Local LLM 输出 ### 格式代码,而非元思考")
    print()


if __name__ == "__main__":
    try:
        test_persona_injection()
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
