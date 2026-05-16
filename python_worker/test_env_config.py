# -*- coding: utf-8 -*-
# test_env_config.py - 验证 .env 配置加载
import os
import sys

# 确保在 python_worker 目录下运行
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print(" AlphaPilot OS 统一配置中心验证")
print("=" * 60)

# 验证 Redis 配置
print("\n Redis 配置 (Upstash):")
redis_url = os.getenv("UPSTASH_REDIS_REST_URL")
redis_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
if redis_url and redis_token:
    print(f"   ✅ UPSTASH_REDIS_REST_URL: {redis_url[:40]}...")
    print(f"   ✅ UPSTASH_REDIS_REST_TOKEN: {redis_token[:20]}...")
else:
    print(f"   ❌ Redis 配置缺失")

# 验证 Local LLM 配置
print("\n Local LLM 配置 (LM Studio):")
llm_base_url = os.getenv("LOCAL_LLM_BASE_URL")
llm_model = os.getenv("LOCAL_LLM_MODEL")
llm_api_type = os.getenv("LOCAL_LLM_API_TYPE")
if llm_base_url and llm_model and llm_api_type:
    print(f"   ✅ LOCAL_LLM_BASE_URL: {llm_base_url}")
    print(f"   ✅ LOCAL_LLM_MODEL: {llm_model}")
    print(f"   ✅ LOCAL_LLM_API_TYPE: {llm_api_type}")
else:
    print(f"   ❌ Local LLM 配置缺失")

# 验证 Worker 配置
print("\n⚙️  Worker 配置:")
worker_id = os.getenv("WORKER_ID", "未设置")
redis_type = os.getenv("REDIS_TYPE", "auto")
use_memory = os.getenv("USE_MEMORY_REDIS", "false")
print(f"   WORKER_ID: {worker_id}")
print(f"   REDIS_TYPE: {redis_type}")
print(f"   USE_MEMORY_REDIS: {use_memory}")

print("\n" + "=" * 60)
print("✅ 配置验证完成")
print("=" * 60)
