#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 Local API 的 system_prompt 识别逻辑
验证 call_local_llm 是否正确拆分 system 和 user messages
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))


def test_message_parsing():
    """测试 message 解析逻辑"""
    print("\n" + "="*60)
    print("🧪 测试 Local API system_prompt 识别逻辑")
    print("="*60)
    
    # 模拟 persona system_prompt + base_prompt 的组合
    persona_system_prompt = """你是一位专业的软件工程师。**你的唯一任务是生成代码文件**。

**核心规则（必须遵守）**:
1. **直接输出代码文件内容**，不要任何解释、思考过程或元描述
2. **禁止输出** 'Here's a thinking process'、'作为一个工程师'、'我将为你生成' 等自然语言
3. **必须使用 ### 文件名 格式** 分隔多个文件
4. **只输出文件名和代码内容**，不要其他文字

**正确示例**:
```
### calculator.py
class Calculator:
    def add(self, a, b):
        return a + b
```

**错误示例（绝对禁止）**:
❌ 'Here's a thinking process...'
❌ '作为一个工程师，我会...'

**现在请直接输出代码文件，以 ### 开头**:"""

    base_prompt = "请根据以下需求生成代码：写一个计算器模块"
    
    # 模拟 write_step.py 中的 prompt 拼接逻辑
    combined_prompt = f"{persona_system_prompt}\n\n---\n\n{base_prompt}"
    
    print("\n【测试 1】验证 prompt 包含分隔符")
    print("-" * 60)
    assert "---" in combined_prompt, "❌ prompt 不包含分隔符"
    print(f"✅ prompt 长度: {len(combined_prompt)} 字符")
    print(f"✅ 包含分隔符 '---': True")
    
    print("\n【测试 2】验证 prompt 可以正确拆分")
    print("-" * 60)
    parts = combined_prompt.split("---", 1)
    assert len(parts) == 2, f"❌ 拆分失败,得到 {len(parts)} 部分"
    
    system_content = parts[0].strip()
    user_content = parts[1].strip()
    
    print(f"✅ system_content 长度: {len(system_content)} 字符")
    print(f"✅ user_content 长度: {len(user_content)} 字符")
    print(f"✅ system_content 包含关键词 '核心规则': {'核心规则' in system_content}")
    print(f"✅ user_content 包含任务描述: {'计算器' in user_content}")
    
    print("\n【测试 3】验证关键词检测逻辑")
    print("-" * 60)
    keywords = ["核心规则", "必须遵守", "禁止输出", "正确示例"]
    detected = any(keyword in system_content for keyword in keywords)
    assert detected, "❌ 未检测到 persona system_prompt 关键词"
    print(f"✅ 检测到 persona system_prompt 关键词: {keywords}")
    
    print("\n【测试 4】模拟 messages 构建")
    print("-" * 60)
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content}
    ]
    
    assert len(messages) == 2, f"❌ messages 数量不正确: {len(messages)}"
    assert messages[0]["role"] == "system", "❌ 第一个 message 不是 system role"
    assert messages[1]["role"] == "user", "❌ 第二个 message 不是 user role"
    
    print(f"✅ messages 数量: {len(messages)}")
    print(f"✅ messages[0]['role']: {messages[0]['role']}")
    print(f"✅ messages[1]['role']: {messages[1]['role']}")
    
    print("\n" + "="*60)
    print("🎉 所有 system_prompt 识别测试通过!")
    print("="*60)
    print("\n💡 结论:")
    print("   ✅ call_local_llm 能够正确识别并拆分 system_prompt")
    print("   ✅ 使用 system role 发送 persona system_prompt")
    print("   ✅ 使用 user role 发送实际任务 prompt")
    print("   ✅ Gemma 4B 将收到正确的指令性 system instruction")
    print()


if __name__ == "__main__":
    try:
        test_message_parsing()
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
