# -*- coding: utf-8 -*-
# test_dual_redis_v28.py
# ---------------------------------------------------------
# AlphaPilot OS v2.8 双云 Redis 架构测试
# 验证根据模型类型自动选择最优 Redis 实例
# ---------------------------------------------------------

import sys
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(os.path.join(os.path.dirname(__file__), 'python_worker', '.env'))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python_worker'))


def test_redis_routing():
    """测试 Redis 路由逻辑"""
    print("\n" + "="*60)
    print("🧪 测试 Redis 路由逻辑")
    print("="*60)
    
    from worker_config import get_redis_type_for_model
    
    test_cases = [
        # 国内模型
        ("deepseek_generate", "tair", "DeepSeek（国内）"),
        ("doubao_analyze", "tair", "Doubao（国内）"),
        ("qwen_write", "tair", "Qwen（国内）"),
        ("ernie_chat", "tair", "文心一言（国内）"),
        ("glm_code", "tair", "智谱 AI（国内）"),
        
        # 国际模型
        ("openai_chat", "upstash", "OpenAI GPT（国际）"),
        ("claude_code", "upstash", "Anthropic Claude（国际）"),
        ("gemini_multimodal", "upstash", "Google Gemini（国际）"),
        ("llama_inference", "upstash", "Meta Llama（国际）"),
    ]
    
    all_passed = True
    
    for model_name, expected_type, description in test_cases:
        actual_type = get_redis_type_for_model(model_name)
        passed = actual_type == expected_type
        status = "✅" if passed else "❌"
        
        if not passed:
            all_passed = False
        
        print(f"\n{status} {model_name}")
        print(f"   描述: {description}")
        print(f"   预期: {expected_type}")
        print(f"   实际: {actual_type}")
    
    print("\n" + "-"*60)
    if all_passed:
        print("✅ 所有路由测试通过！")
    else:
        print("❌ 部分路由测试失败")
    
    return all_passed


def test_upstash_connection():
    """测试 Upstash Redis 连接"""
    print("\n" + "="*60)
    print("🔍 测试 Upstash Redis（国际模型）")
    print("="*60)
    
    try:
        from worker_config import create_redis_client
        
        redis = create_redis_client("upstash")
        
        print(f"\n✅ Redis 实例: {redis}")
        
        # Ping 测试
        ping_result = redis.ping()
        print(f"✅ Ping 结果: {ping_result}")
        
        # SET/GET 测试
        redis.set("test:v28:upstash", "international")
        value = redis.get("test:v28:upstash")
        print(f"✅ SET/GET 测试: test:v28:upstash = {value}")
        
        # 清理
        redis.delete("test:v28:upstash")
        
        print(f"\n💡 Upstash Redis 工作正常（国际模型）")
        return True
        
    except Exception as e:
        print(f"\n❌ Upstash Redis 连接失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tair_connection():
    """测试阿里云 Tair Redis 连接"""
    print("\n" + "="*60)
    print("🔍 测试阿里云 Tair Redis（国内模型）")
    print("="*60)
    
    try:
        from worker_config import create_redis_client
        
        redis = create_redis_client("tair")
        
        print(f"\n✅ Redis 实例: {redis}")
        
        # Ping 测试
        ping_result = redis.ping()
        print(f"✅ Ping 结果: {ping_result}")
        
        # SET/GET 测试
        redis.set("test:v28:tair", "domestic")
        value = redis.get("test:v28:tair")
        print(f"✅ SET/GET 测试: test:v28:tair = {value}")
        
        # 清理
        redis.delete("test:v28:tair")
        
        print(f"\n💡 阿里云 Tair Redis 工作正常（国内模型）")
        return True
        
    except Exception as e:
        print(f"\n❌ 阿里云 Tair Redis 连接失败: {e}")
        print(f"\n💡 可能原因:")
        print(f"  1. 公网地址未申请完成")
        print(f"  2. 白名单未配置")
        print(f"  3. 网络不通（防火墙/代理）")
        import traceback
        traceback.print_exc()
        return False


def test_auto_routing():
    """测试自动路由功能"""
    print("\n" + "="*60)
    print("🧪 测试自动路由功能")
    print("="*60)
    
    try:
        from worker_config import create_redis_client
        
        # 测试国内模型自动选择 Tair
        print(f"\n⏳ 测试国内模型 (deepseek)...")
        redis_domestic = create_redis_client(model_name="deepseek_generate")
        print(f"✅ 国内模型 Redis: {type(redis_domestic).__name__}")
        
        # 测试国际模型自动选择 Upstash
        print(f"\n⏳ 测试国际模型 (openai)...")
        redis_international = create_redis_client(model_name="openai_chat")
        print(f"✅ 国际模型 Redis: {type(redis_international).__name__}")
        
        print(f"\n💡 自动路由功能正常")
        return True
        
    except Exception as e:
        print(f"\n❌ 自动路由测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("\n" + "="*60)
    print("🚀 AlphaPilot OS v2.8 - 双云 Redis 架构测试")
    print("="*60)
    
    print("\n📋 测试目标:")
    print("  1. 验证 Redis 路由逻辑正确")
    print("  2. 验证 Upstash Redis（国际模型）正常工作")
    print("  3. 验证阿里云 Tair Redis（国内模型）正常工作")
    print("  4. 验证自动路由功能")
    
    # 1. 测试路由逻辑
    print("\n" + "-"*60)
    routing_ok = test_redis_routing()
    
    # 2. 测试 Upstash
    print("\n" + "-"*60)
    upstash_ok = test_upstash_connection()
    
    # 3. 测试 Tair
    print("\n" + "-"*60)
    tair_ok = test_tair_connection()
    
    # 4. 测试自动路由
    if routing_ok:
        print("\n" + "-"*60)
        auto_ok = test_auto_routing()
    else:
        print("\n⚠️ 跳过自动路由测试（路由逻辑失败）")
        auto_ok = False
    
    # 总结
    print("\n" + "="*60)
    print("📊 测试结果总结")
    print("="*60)
    print(f"\n✅ Redis 路由逻辑: {'通过' if routing_ok else '失败'}")
    print(f"✅ Upstash Redis (国际): {'正常' if upstash_ok else '异常'}")
    print(f"✅ 阿里云 Tair (国内): {'正常' if tair_ok else '异常'}")
    print(f"✅ 自动路由功能: {'通过' if auto_ok else '失败'}")
    
    print("\n💡 架构说明:")
    print("  - 国内模型 (DeepSeek/Doubao/Qwen) → 阿里云 Tair（国内加速）")
    print("  - 国际模型 (OpenAI/Claude/Gemini) → Upstash（全球 CDN）")
    print("  - 自动路由: 根据模型名称智能选择最优 Redis")
    
    print("\n🎯 下一步建议:")
    if routing_ok and upstash_ok and auto_ok:
        if tair_ok:
            print("  ✅ 双云架构完全就绪！可以开始使用")
            print("  📝 使用方法:")
            print("     1. 保持 REDIS_TYPE=auto（自动模式）")
            print("     2. Worker 会根据模型自动选择 Redis")
            print("     3. 无需手动配置，开箱即用")
        else:
            print("  ⚠️ 阿里云 Tair 连接失败，请检查:")
            print("     1. 公网地址是否申请完成")
            print("     2. 白名单是否配置")
            print("     3. 网络连接是否正常")
            print("  💡 临时方案: 设置 REDIS_TYPE=upstash 全部使用 Upstash")
    else:
        print("  ❌ 部分测试失败，请检查配置")
    
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
