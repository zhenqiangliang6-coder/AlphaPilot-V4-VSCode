# -*- coding: utf-8 -*-
# test_local_llm.py
# ---------------------------------------------------------
# Local LLM Worker v3.0 - 连接测试脚本
# - 测试 Ollama API 连接
# - 测试基本的文本生成
# ---------------------------------------------------------

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from agents.local_llm.local_api import call_local_llm, test_connection


def main():
    print("=" * 60)
    print("🧪 Local LLM Worker v3.0 - 连接测试")
    print("=" * 60)
    
    # 1. 测试连接
    print("\n📡 步骤 1: 测试 Ollama 连接...")
    if not test_connection():
        print("\n❌ 测试失败：无法连接到 Ollama 服务")
        print("💡 请确保：")
        print("   1. Ollama 已安装并运行")
        print("   2. gemma2:2b 模型已下载（ollama pull gemma2:2b）")
        print("   3. Ollama 服务运行在 http://localhost:11434")
        return False
    
    # 2. 测试基本对话
    print("\n💬 步骤 2: 测试基本对话...")
    try:
        response = call_local_llm("你好，请介绍一下你自己。", stream=False)
        print(f"\n✅ 响应成功:\n{response}\n")
    except Exception as e:
        print(f"\n❌ 对话测试失败: {e}")
        return False
    
    # 3. 测试代码生成
    print("\n💻 步骤 3: 测试代码生成...")
    try:
        code_prompt = "请写一个简单的 Python 函数来计算斐波那契数列的前10个数。"
        response = call_local_llm(code_prompt, stream=False)
        print(f"\n✅ 代码生成成功:\n{response}\n")
    except Exception as e:
        print(f"\n❌ 代码生成测试失败: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！Local LLM Worker 可以正常使用。")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
