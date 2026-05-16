# -*- coding: utf-8 -*-
# test_tair_simple.py
# ---------------------------------------------------------
# 简单测试阿里云 Tair Redis 连接
# ---------------------------------------------------------

import redis
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv('python_worker/.env')

# 获取配置
tair_host = os.getenv("TAIR_HOST")
tair_port = int(os.getenv("TAIR_PORT", "6379"))
tair_password = os.getenv("TAIR_PASSWORD")

print("="*60)
print("🔍 测试阿里云 Tair Redis 连接")
print("="*60)
print(f"\n配置信息:")
print(f"  Host: {tair_host}")
print(f"  Port: {tair_port}")
print(f"  Password: {'*' * len(tair_password) if tair_password else '未设置'}")

try:
    print(f"\n⏳ 正在连接...")
    
    # 创建 Redis 客户端
    r = redis.Redis(
        host=tair_host,
        port=tair_port,
        password=tair_password,
        ssl=True,
        ssl_cert_reqs=None,  # 跳过证书验证
        decode_responses=True,
        socket_timeout=10,  # 设置超时时间
        socket_connect_timeout=10
    )
    
    # Ping 测试
    print(f"⏳ 执行 Ping...")
    result = r.ping()
    print(f"✅ Ping 结果: {result}")
    
    # SET/GET 测试
    print(f"\n⏳ 执行 SET/GET...")
    r.set("test:tair_simple", "hello_tair")
    value = r.get("test:tair_simple")
    print(f"✅ SET/GET 结果: {value}")
    
    # 清理
    r.delete("test:tair_simple")
    
    print(f"\n✅ 阿里云 Tair Redis 连接成功！")
    
except Exception as e:
    print(f"\n❌ 连接失败: {e}")
    print(f"\n💡 可能原因:")
    print(f"  1. 网络连接问题（防火墙/代理）")
    print(f"  2. Tair 实例地址或密码错误")
    print(f"  3. Tair 实例未启用或未授权访问")
    print(f"  4. SSL/TLS 配置问题")
