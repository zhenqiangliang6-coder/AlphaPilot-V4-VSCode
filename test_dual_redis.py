# -*- coding: utf-8 -*-
# test_dual_redis.py
# ---------------------------------------------------------
# 双 Redis 架构测试
# 验证 Upstash 和阿里云 Tair 可以同时运行，互不干扰
# ---------------------------------------------------------

import sys
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(os.path.join(os.path.dirname(__file__), 'python_worker', '.env'))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python_worker'))


def test_upstash_redis():
    """测试 Upstash Redis（生产环境）"""
    print("\n" + "="*60)
    print("🔍 测试 Upstash Redis（生产环境）")
    print("="*60)
    
    try:
        from worker_config import create_redis_client
        
        # 显式指定使用 Upstash
        redis = create_redis_client("upstash")
        
        print(f"\n✅ Redis 实例: {redis}")
        
        # Ping 测试
        ping_result = redis.ping()
        print(f"✅ Ping 结果: {ping_result}")
        
        # SET/GET 测试
        redis.set("test:upstash", "production")
        value = redis.get("test:upstash")
        print(f"✅ SET/GET 测试: test:upstash = {value}")
        
        # 清理
        redis.delete("test:upstash")
        
        print(f"\n💡 Upstash Redis 工作正常（生产环境）")
        return True
        
    except Exception as e:
        print(f"\n❌ Upstash Redis 连接失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tair_redis():
    """测试阿里云 Tair Redis（测试环境）"""
    print("\n" + "="*60)
    print("🔍 测试阿里云 Tair Redis（测试环境）")
    print("="*60)
    
    try:
        from worker_config import create_redis_client
        
        # 显式指定使用 Tair
        redis = create_redis_client("tair")
        
        print(f"\n✅ Redis 实例: {redis}")
        
        # Ping 测试
        ping_result = redis.ping()
        print(f"✅ Ping 结果: {ping_result}")
        
        # SET/GET 测试
        redis.set("test:tair", "testing")
        value = redis.get("test:tair")
        print(f"✅ SET/GET 测试: test:tair = {value}")
        
        # 清理
        redis.delete("test:tair")
        
        print(f"\n💡 阿里云 Tair Redis 工作正常（测试环境）")
        return True
        
    except Exception as e:
        print(f"\n❌ 阿里云 Tair Redis 连接失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_isolation():
    """测试两个 Redis 实例的隔离性"""
    print("\n" + "="*60)
    print("🔍 测试 Redis 实例隔离性")
    print("="*60)
    
    try:
        from worker_config import create_redis_client
        
        # 创建两个独立的 Redis 客户端
        upstash = create_redis_client("upstash")
        tair = create_redis_client("tair")
        
        # 在 Upstash 中设置 key
        upstash.set("isolation:test", "upstash_value")
        
        # 在 Tair 中设置相同的 key
        tair.set("isolation:test", "tair_value")
        
        # 分别读取，验证隔离
        upstash_value = upstash.get("isolation:test")
        tair_value = tair.get("isolation:test")
        
        print(f"\n📊 隔离性测试结果:")
        print(f"   Upstash isolation:test = {upstash_value}")
        print(f"   Tair    isolation:test = {tair_value}")
        
        if upstash_value == "upstash_value" and tair_value == "tair_value":
            print(f"\n✅ 隔离性测试通过！两个 Redis 实例完全独立")
            success = True
        else:
            print(f"\n❌ 隔离性测试失败！数据可能混淆")
            success = False
        
        # 清理
        upstash.delete("isolation:test")
        tair.delete("isolation:test")
        
        return success
        
    except Exception as e:
        print(f"\n❌ 隔离性测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("\n" + "="*60)
    print("🚀 AlphaPilot OS - 双 Redis 架构测试")
    print("="*60)
    
    print("\n📋 测试目标:")
    print("  1. 验证 Upstash Redis（生产环境）正常工作")
    print("  2. 验证阿里云 Tair Redis（测试环境）正常工作")
    print("  3. 验证两个 Redis 实例完全隔离，互不干扰")
    
    # 1. 测试 Upstash
    print("\n" + "-"*60)
    upstash_ok = test_upstash_redis()
    
    # 2. 测试 Tair
    print("\n" + "-"*60)
    tair_ok = test_tair_redis()
    
    # 3. 测试隔离性
    if upstash_ok and tair_ok:
        print("\n" + "-"*60)
        isolation_ok = test_isolation()
    else:
        print("\n⚠️ 跳过隔离性测试（某个 Redis 连接失败）")
        isolation_ok = False
    
    # 总结
    print("\n" + "="*60)
    print("📊 测试结果总结")
    print("="*60)
    print(f"\n✅ Upstash Redis (生产): {'正常' if upstash_ok else '异常'}")
    print(f"✅ 阿里云 Tair (测试): {'正常' if tair_ok else '异常'}")
    print(f"✅ 实例隔离性: {'通过' if isolation_ok else '失败'}")
    
    print("\n💡 架构说明:")
    print("  - Qwen Worker → Upstash Redis（稳定，不改）")
    print("  - DeepSeek Worker → 阿里云 Tair（测试新架构）")
    print("  - Doubao Worker → 阿里云 Tair（测试新架构）")
    print("  - 两个 Redis 完全独立，互不干扰 ✅")
    
    print("\n🎯 下一步建议:")
    if upstash_ok and tair_ok and isolation_ok:
        print("  ✅ 双 Redis 架构验证成功！可以开始使用")
        print("  📝 使用方法:")
        print("     1. Qwen Worker 保持 REDIS_TYPE=upstash")
        print("     2. DeepSeek/Doubao Worker 设置 REDIS_TYPE=tair")
        print("     3. 通过环境变量或启动脚本控制")
    else:
        print("  ⚠️ 部分测试失败，请检查配置")
    
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
