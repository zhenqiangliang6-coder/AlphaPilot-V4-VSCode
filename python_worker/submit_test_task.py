# -*- coding: utf-8 -*-
"""
submit_test_task.py
---------------------------------------------------------
快速提交测试任务到队列

使用方法：
    python submit_test_task.py
"""

import os
import sys
import json
import time
from dotenv import load_dotenv

load_dotenv()

from upstash_redis import Redis

# 初始化 Redis
redis = Redis(
    url=os.getenv("UPSTASH_REDIS_REST_URL"),
    token=os.getenv("UPSTASH_REDIS_REST_TOKEN")
)

# 创建测试任务
task_id = f"test-{int(time.time())}"
task = {
    "task_id": task_id,
    "task_type": "qwen_generate",
    "payload": {
        "prompt": "请用 Python 写一个简单的 hello world 函数"
    },
    "steps": [],
    "events": [],
    "context": {}
}

# 提交到队列
queue_name = "task_queue:qwen"
redis.lpush(queue_name, json.dumps(task))

print(f"✅ 任务已提交")
print(f"   任务 ID: {task_id}")
print(f"   队列: {queue_name}")
print(f"   队列长度: {redis.llen(queue_name)}")
print(f"\n提示: 确保 qwen-worker 正在运行")
