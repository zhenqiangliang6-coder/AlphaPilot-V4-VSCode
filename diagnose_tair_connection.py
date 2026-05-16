# -*- coding: utf-8 -*-
# diagnose_tair_connection.py
# ---------------------------------------------------------
# 详细诊断阿里云 Tair Redis 公网连接问题
# ---------------------------------------------------------

import sys
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv('python_worker/.env')

print("="*60)
print("🔍 阿里云 Tair Redis 公网连接详细诊断")
print("="*60)

# 获取配置
tair_host = os.getenv("TAIR_HOST")
tair_port = int(os.getenv("TAIR_PORT", "6379"))
tair_password = os.getenv("TAIR_PASSWORD")

print(f"\n📋 配置信息:")
print(f"  Host: {tair_host}")
print(f"  Port: {tair_port}")
print(f"  Password: {'*' * len(tair_password) if tair_password else '未设置'}")

# 测试 1: TCP 连通性
print("\n" + "-"*60)
print("🧪 测试 1: TCP 端口连通性")
print("-"*60)

try:
    import socket
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    
    result = sock.connect_ex((tair_host, tair_port))
    sock.close()
    
    if result == 0:
        print(f"✅ TCP 端口 {tair_port} 可达")
    else:
        print(f"❌ TCP 端口 {tair_port} 不可达（错误码: {result}）")
        
except Exception as e:
    print(f"❌ TCP 测试异常: {e}")

# 测试 2: 尝试多种 SSL 配置
print("\n" + "-"*60)
print("🧪 测试 2: 尝试不同的 SSL 配置")
print("-"*60)

import redis

test_configs = [
    {"ssl": True, "ssl_cert_reqs": None, "desc": "SSL=True, 跳过证书验证"},
    {"ssl": True, "ssl_cert_reqs": "required", "desc": "SSL=True, 严格证书验证"},
    {"ssl": False, "desc": "SSL=False, 不使用加密"},
]

for config in test_configs:
    desc = config.pop("desc")
    print(f"\n⏳ 测试: {desc}")
    
    try:
        r = redis.Redis(
            host=tair_host,
            port=tair_port,
            password=tair_password,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            **config
        )
        
        result = r.ping()
        print(f"✅ 成功！Ping 结果: {result}")
        print(f"💡 请使用此配置:")
        print(f"   ssl={config.get('ssl', False)}")
        if 'ssl_cert_reqs' in config:
            print(f"   ssl_cert_reqs={config['ssl_cert_reqs']}")
        break
        
    except redis.exceptions.AuthenticationError:
        print(f"❌ 认证失败（密码错误）")
        break
        
    except redis.exceptions.TimeoutError:
        print(f"❌ 连接超时")
        
    except Exception as e:
        print(f"❌ 错误: {type(e).__name__}: {str(e)[:100]}")

print("\n" + "="*60)
print("💡 如果所有测试都失败，请检查:")
print("  1. 阿里云控制台 TLS/SSL 设置是否启用")
print("  2. 白名单是否包含你的公网 IP")
print("  3. 密码是否正确（可在控制台重置）")
print("="*60)
