# -*- coding: utf-8 -*-
# diagnose_tair.py
# ---------------------------------------------------------
# 阿里云 Tair Redis 实例诊断工具
# 帮助你系统性地排查连接问题
# ---------------------------------------------------------

import sys
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv('python_worker/.env')

def print_section(title):
    """打印分隔线"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)


def check_env_config():
    """检查环境变量配置"""
    print_section("📋 第一步：检查环境变量配置")
    
    tair_host = os.getenv("TAIR_HOST")
    tair_port = os.getenv("TAIR_PORT", "6379")
    tair_password = os.getenv("TAIR_PASSWORD")
    tair_tls = os.getenv("TAIR_TLS", "true")
    
    print(f"\n✅ TAIR_HOST: {tair_host or '❌ 未设置'}")
    print(f"✅ TAIR_PORT: {tair_port}")
    print(f"✅ TAIR_PASSWORD: {'*' * 8 if tair_password else '❌ 未设置'}")
    print(f"✅ TAIR_TLS: {tair_tls}")
    
    if not tair_host or not tair_password:
        print("\n❌ 配置不完整！请在 .env 文件中设置 TAIR_HOST 和 TAIR_PASSWORD")
        return False
    
    print("\n💡 配置检查通过")
    return True


def check_network_connectivity():
    """检查网络连通性"""
    print_section("🔗 第二步：检查网络连通性")
    
    tair_host = os.getenv("TAIR_HOST")
    tair_port = int(os.getenv("TAIR_PORT", "6379"))
    
    print(f"\n⏳ 测试连接到 {tair_host}:{tair_port}...")
    
    try:
        import socket
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)  # 5秒超时
        
        result = sock.connect_ex((tair_host, tair_port))
        sock.close()
        
        if result == 0:
            print(f"✅ 网络连通性正常（TCP 端口 {tair_port} 可达）")
            return True
        else:
            print(f"❌ 网络连通性失败（错误码: {result}）")
            print(f"\n💡 可能原因:")
            print(f"  1. 防火墙阻止了连接")
            print(f"  2. 代理配置问题")
            print(f"  3. 实例不在公网（VPC 内网）")
            print(f"  4. 白名单未配置")
            return False
            
    except Exception as e:
        print(f"❌ 网络测试异常: {e}")
        return False


def check_redis_connection():
    """测试 Redis 连接"""
    print_section("🔍 第三步：测试 Redis 连接")
    
    try:
        import redis
        
        tair_host = os.getenv("TAIR_HOST")
        tair_port = int(os.getenv("TAIR_PORT", "6379"))
        tair_password = os.getenv("TAIR_PASSWORD")
        tair_tls = os.getenv("TAIR_TLS", "true").lower() == "true"
        
        print(f"\n⏳ 创建 Redis 客户端...")
        
        # 创建连接
        r = redis.Redis(
            host=tair_host,
            port=tair_port,
            password=tair_password,
            ssl=tair_tls,
            ssl_cert_reqs=None,  # 跳过证书验证
            decode_responses=True,
            socket_timeout=10,
            socket_connect_timeout=10
        )
        
        print(f"✅ Redis 客户端创建成功")
        
        # Ping 测试
        print(f"\n⏳ 执行 PING 命令...")
        result = r.ping()
        print(f"✅ PING 结果: {result}")
        
        # SET/GET 测试
        print(f"\n⏳ 执行 SET/GET 测试...")
        r.set("diagnose:test", "hello_tair")
        value = r.get("diagnose:test")
        print(f"✅ SET/GET 结果: {value}")
        
        # 清理
        r.delete("diagnose:test")
        
        print(f"\n✅ Redis 连接测试成功！")
        return True
        
    except redis.exceptions.AuthenticationError:
        print(f"\n❌ 认证失败！密码可能不正确")
        print(f"\n💡 解决方法:")
        print(f"  1. 在阿里云控制台重置密码")
        print(f"  2. 更新 .env 文件中的 TAIR_PASSWORD")
        return False
        
    except redis.exceptions.TimeoutError:
        print(f"\n❌ 连接超时！")
        print(f"\n💡 可能原因:")
        print(f"  1. 网络不通（见第二步）")
        print(f"  2. 白名单未配置")
        print(f"  3. 实例已停止或过期")
        return False
        
    except Exception as e:
        print(f"\n❌ 连接失败: {type(e).__name__}: {e}")
        return False


def provide_troubleshooting_guide():
    """提供故障排查指南"""
    print_section("📖 故障排查指南")
    
    print("\n如果以上测试失败，请按以下步骤排查：\n")
    
    print("1️⃣  登录阿里云控制台")
    print("   网址: https://kvstore.console.aliyun.com/")
    print("   操作: 找到你的 Redis 实例\n")
    
    print("2️⃣  检查实例状态")
    print("   - 状态必须是 'Running'")
    print("   - 如果显示 'Locked' 或 'Expired'，需要续费\n")
    
    print("3️⃣  检查白名单")
    print("   - 左侧菜单: 白名单设置")
    print("   - 添加你的公网 IP 到白名单")
    print("   - 或临时添加 0.0.0.0/0 用于测试\n")
    
    print("4️⃣  检查网络连接")
    print("   PowerShell: Test-NetConnection <host> -Port 6379")
    print("   如果失败，检查防火墙和代理\n")
    
    print("5️⃣  重置密码（如果怀疑密码错误）")
    print("   - 实例详情页 → 重置密码")
    print("   - 更新 .env 文件\n")
    
    print("6️⃣  检查实例是否过期")
    print("   - 查看 '到期时间'")
    print("   - 如果已过期，需要续费\n")


def main():
    """主函数"""
    print("\n" + "="*60)
    print("🚀 阿里云 Tair Redis 实例诊断工具")
    print("="*60)
    print("\n本工具将帮助你系统性地排查 Tair 连接问题\n")
    
    # 1. 检查配置
    config_ok = check_env_config()
    if not config_ok:
        return
    
    # 2. 检查网络
    network_ok = check_network_connectivity()
    
    # 3. 测试 Redis 连接
    if network_ok:
        redis_ok = check_redis_connection()
    else:
        print("\n⚠️ 跳过 Redis 连接测试（网络不通）")
        redis_ok = False
    
    # 4. 总结
    print_section("📊 诊断结果总结")
    
    print(f"\n✅ 配置检查: {'通过' if config_ok else '失败'}")
    print(f"✅ 网络连通: {'通过' if network_ok else '失败'}")
    print(f"✅ Redis 连接: {'通过' if redis_ok else '失败'}")
    
    if config_ok and network_ok and redis_ok:
        print("\n🎉 恭喜！Tair Redis 实例工作正常！")
        print("\n💡 下一步:")
        print("  - 在 .env 中设置 REDIS_TYPE=tair")
        print("  - 启动 DeepSeek/Doubao Worker 进行测试")
    else:
        print("\n⚠️ 存在问题，请参考下方的故障排查指南")
        provide_troubleshooting_guide()
    
    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 诊断已中断")
    except Exception as e:
        print(f"\n❌ 诊断失败: {e}")
        import traceback
        traceback.print_exc()
