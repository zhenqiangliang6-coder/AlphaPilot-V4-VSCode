# -*- coding: utf-8 -*-
# ddca.py - Redis 连接测试脚本
# ---------------------------------------------------------
# 用于测试云 Redis (Tair) 连接
# ---------------------------------------------------------

import sys
import os

# 添加父目录到 Python 路径
sys.path.insert(0, os.path.dirname(__file__))

from worker_config import redis

# 测试 Redis 连接
try:
    print("🔍 正在测试 Redis 连接...")
    print(f"   Redis 实例: {redis}")
    
    # 测试 ping
    ping_result = redis.ping()
    print(f"✅ Ping 结果: {ping_result}")
    
    # 测试 set/get
    print("\n📝 测试 SET/GET 操作...")
    set_result = redis.set("hello", "tair")
    print(f"   SET hello=tair: {set_result}")
    
    get_result = redis.get("hello")
    print(f"   GET hello: {get_result}")
    
    # 清理测试数据
    redis.delete("hello")
    print(f"\n✅ Redis 连接测试成功！")
    
except Exception as e:
    print(f"\n❌ Redis 连接失败: {e}")
    print(f"   错误类型: {type(e).__name__}")
    import traceback
    traceback.print_exc()
