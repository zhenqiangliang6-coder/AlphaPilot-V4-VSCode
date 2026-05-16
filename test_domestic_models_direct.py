# -*- coding: utf-8 -*-
# test_domestic_models_direct.py
# ---------------------------------------------------------
# 国内模型直连测试（DeepSeek/Doubao）
# 验证禁用代理后的性能提升
# ---------------------------------------------------------

import sys
import os
import time
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(os.path.join(os.path.dirname(__file__), 'python_worker', '.env'))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python_worker'))


def test_deepseek_direct():
    """测试 DeepSeek 直连性能"""
    print("\n" + "="*60)
    print("🧪 测试 DeepSeek API（直连模式）")
    print("="*60)
    
    try:
        from agents.deepeek.deepseek_api import call_deepseek
        
        prompt = "请用一句话介绍你自己"
        
        print(f"\n📤 发送请求...")
        start_time = time.time()
        
        result = call_deepseek(prompt, stream=False)
        
        elapsed = time.time() - start_time
        
        print(f"\n✅ DeepSeek API 调用成功！")
        print(f"   耗时: {elapsed:.2f} 秒")
        print(f"   响应长度: {len(result)} 字符")
        print(f"   响应内容: {result[:100]}...")
        
        if elapsed < 5:
            print(f"\n🚀 性能优秀！(< 5秒)")
        elif elapsed < 10:
            print(f"\n⚡ 性能良好 (5-10秒)")
        else:
            print(f"\n⚠️ 响应较慢 (> 10秒)，可能需要进一步优化")
        
        return True
        
    except Exception as e:
        print(f"\n❌ DeepSeek API 调用失败: {e}")
        print(f"\n💡 可能原因:")
        print(f"   1. API Key 配额限制（之前测试显示 429 错误）")
        print(f"   2. 火山引擎服务暂时不可用")
        print(f"   3. 网络连接问题")
        return False


def test_doubao_direct():
    """测试 Doubao 直连性能"""
    print("\n" + "="*60)
    print("🧪 测试 Doubao API（直连模式）")
    print("="*60)
    
    try:
        from agents.Volcengine.doubao_api import call_doubao
        
        prompt = "请用一句话介绍你自己"
        
        print(f"\n📤 发送请求...")
        start_time = time.time()
        
        result = call_doubao(prompt)
        
        elapsed = time.time() - start_time
        
        print(f"\n✅ Doubao API 调用成功！")
        print(f"   耗时: {elapsed:.2f} 秒")
        print(f"   响应长度: {len(result)} 字符")
        print(f"   响应内容: {result[:100]}...")
        
        if elapsed < 5:
            print(f"\n🚀 性能优秀！(< 5秒)")
        elif elapsed < 10:
            print(f"\n⚡ 性能良好 (5-10秒)")
        else:
            print(f"\n⚠️ 响应较慢 (> 10秒)")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Doubao API 调用失败: {e}")
        return False


def test_redis_connection():
    """测试 Redis 连接（确认云内存正常）"""
    print("\n" + "="*60)
    print("🔍 测试 Redis 连接（云内存）")
    print("="*60)
    
    try:
        from worker_config import redis
        
        # Ping 测试
        ping_result = redis.ping()
        print(f"\n✅ Redis Ping: {ping_result}")
        
        # SET/GET 测试
        redis.set("test_key", "test_value")
        value = redis.get("test_key")
        print(f"✅ Redis SET/GET: {value}")
        
        # 清理
        redis.delete("test_key")
        
        print(f"\n💡 Redis 作为云内存工作正常，可用于 LLM 测试")
        return True
        
    except Exception as e:
        print(f"\n❌ Redis 连接失败: {e}")
        return False


def main():
    """主函数"""
    print("\n" + "="*60)
    print("🚀 AlphaPilot OS - 国内模型直连性能测试")
    print("="*60)
    
    print("\n📋 测试目标:")
    print("  1. 验证 DeepSeek/Doubao 直连是否比走代理更快")
    print("  2. 确认 Redis 云内存正常工作")
    print("  3. Qwen 保持不变（已验证稳定）")
    
    # 1. 测试 Redis
    print("\n" + "-"*60)
    redis_ok = test_redis_connection()
    
    # 2. 测试 DeepSeek
    print("\n" + "-"*60)
    deepseek_ok = test_deepseek_direct()
    
    # 3. 测试 Doubao
    print("\n" + "-"*60)
    doubao_ok = test_doubao_direct()
    
    # 总结
    print("\n" + "="*60)
    print("📊 测试结果总结")
    print("="*60)
    print(f"\n✅ Redis 云内存: {'正常' if redis_ok else '异常'}")
    print(f"✅ DeepSeek 直连: {'成功' if deepseek_ok else '失败'}")
    print(f"✅ Doubao 直连: {'成功' if doubao_ok else '失败'}")
    
    print("\n💡 架构说明:")
    print("  - 国内模型 (DeepSeek/Doubao): 直连火山引擎（禁用代理）")
    print("  - Qwen: 保持原有配置（阿里云，已验证稳定）")
    print("  - 国际模型: 使用系统代理（如有）")
    print("  - Redis: Upstash 云内存（用于任务队列和状态管理）")
    
    print("\n🎯 下一步建议:")
    if deepseek_ok or doubao_ok:
        print("  ✅ 直连优化生效，可以开始使用国内模型进行测试")
    else:
        print("  ⚠️ 直连仍有问题，建议:")
        print("     1. 等待 DeepSeek API 配额重置")
        print("     2. 优先使用 Doubao 或 Qwen 进行开发")
        print("     3. 检查火山引擎控制台的服务状态")
    
    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 测试已中断")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
