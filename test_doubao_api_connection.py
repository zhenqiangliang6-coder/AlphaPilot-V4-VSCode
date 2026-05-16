# -*- coding: utf-8 -*-
"""
测试 Doubao API 是否正常工作
"""

import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv('python_worker/.env')

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python_worker'))

from python_worker.agents.Volcengine.doubao_api import call_doubao, call_doubao_stream

def test_non_stream():
    """测试非流式调用"""
    print("=" * 80)
    print("🧪 测试 1: 非流式调用")
    print("=" * 80)
    
    prompt = "用一句话介绍你自己"
    
    try:
        result = call_doubao(prompt)
        print(f"✅ 成功！返回长度: {len(result)} 字符")
        print(f"内容预览: {result[:200]}")
        return True
    except Exception as e:
        print(f"❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_stream():
    """测试流式调用"""
    print("\n" + "=" * 80)
    print("🧪 测试 2: 流式调用")
    print("=" * 80)
    
    prompt = "用一句话介绍你自己"
    
    try:
        result = ""
        for chunk in call_doubao_stream(prompt):
            result += chunk
            print(chunk, end="", flush=True)
        
        print(f"\n\n✅ 成功！总长度: {len(result)} 字符")
        return True
    except Exception as e:
        print(f"\n❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("🚀 Doubao API 连接测试")
    print(f"API Key: {'已配置' if os.getenv('VOLC_API_KEY') else '未配置'}")
    print(f"Model: doubao-seed-2-0-lite-260215")
    print()
    
    # 测试非流式
    success1 = test_non_stream()
    
    # 测试流式
    success2 = test_stream()
    
    print("\n" + "=" * 80)
    print("📊 测试结果汇总")
    print("=" * 80)
    print(f"非流式调用: {'✅ 通过' if success1 else '❌ 失败'}")
    print(f"流式调用:   {'✅ 通过' if success2 else '❌ 失败'}")
    
    if not (success1 and success2):
        print("\n⚠️  建议检查:")
        print("   1. VOLC_API_KEY 是否正确")
        print("   2. 网络连接是否正常")
        print("   3. API 端点是否可达")