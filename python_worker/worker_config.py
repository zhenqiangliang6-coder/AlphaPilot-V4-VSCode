# -*- coding: utf-8 -*-
# worker_config.py
# ---------------------------------------------------------
# Worker 基础配置、Redis、流式输出、上下文结构
# ---------------------------------------------------------

import os
import time
import json
import requests
from dotenv import load_dotenv

# ⭐ 加载 .env 文件（支持从任何目录运行）
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

# =========================
# ⭐ 新增：内存模式开关（用于调试）
# =========================

USE_MEMORY_REDIS = os.getenv("USE_MEMORY_REDIS", "false").lower() == "true"

# =========================
# 基础配置
# =========================

if USE_MEMORY_REDIS:
    # ⭐ 内存模式：使用简单的字典模拟 Redis
    print("⚠️  使用内存模式（绕过云 Redis）")
    
    class MemoryRedis:
        """内存 Redis 模拟器"""
        def __init__(self):
            self.data = {}
        
        def ping(self):
            return True
        
        def set(self, key, value):
            self.data[key] = str(value)
            return "OK"
        
        def get(self, key):
            return self.data.get(key)
        
        def delete(self, key):
            if key in self.data:
                del self.data[key]
            return 1
        
        def lpush(self, key, *values):
            if key not in self.data:
                self.data[key] = []
            # 确保值是字符串
            str_values = [str(v) for v in values]
            self.data[key] = str_values + self.data[key]
            return len(self.data[key])
        
        def rpop(self, key):
            if key in self.data and self.data[key]:
                return self.data[key].pop()
            return None
        
        def llen(self, key):
            return len(self.data.get(key, []))
    
    redis = MemoryRedis()
else:
    # ⭐ 云 Redis 模式：使用 Upstash
    from upstash_redis import Redis
    redis = Redis(
        url=os.getenv("UPSTASH_REDIS_REST_URL"),
        token=os.getenv("UPSTASH_REDIS_REST_TOKEN")
    )

NODE_API_URL = os.getenv("NODE_API_URL", "http://localhost:3000")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
WORKER_ID = os.getenv("WORKER_ID", "qwen-worker-1")

# =========================
# ⭐ 新增：按模型类型隔离队列（符合多智能体架构）
# =========================

# Worker 与队列的映射关系（协议宪法扩展）
WORKER_QUEUE_MAP = {
    "qwen": "task_queue:qwen",
    "deepseek": "task_queue:deepseek", 
    "doubao": "task_queue:doubao",
    # 未来扩展
    "claude": "task_queue:claude",
    "gemini": "task_queue:gemini",
    "openai": "task_queue:openai",
}

def get_worker_queue(task_type: str) -> str:
    """
    根据任务类型获取对应的队列名称
    
    参数:
        task_type: 任务类型 (如 "qwen_generate", "deepseek_generate")
    
    返回:
        str: 队列名称
    
    示例:
        "qwen_generate" → "task_queue:qwen"
        "deepseek_analyze" → "task_queue:deepseek"
    
    设计原则:
        - 尊重 Worker 的真相地位：每个 Worker 只处理自己的任务
        - 符合多智能体架构愿景：为每个 agent 提供专属执行环境
        - 向后兼容：未知类型回退到默认队列
    """
    # 提取模型前缀 (qwen/deepseek/doubao 等)
    model_prefix = task_type.split("_")[0]
    
    # 查找映射，如果没有则使用默认队列（向后兼容）
    return WORKER_QUEUE_MAP.get(model_prefix, "task_queue")

# =========================
# ⭐ 新增：任务取消机制（线程安全）
# =========================

STOP_FLAGS = {}  # { task_id: True/False } - 内存中的取消标记


def check_stop_flag(task_id: str) -> bool:
    """
    检查任务是否被取消
    
    参数:
        task_id: 任务 ID
    
    返回:
        bool: True 表示任务已被取消，False 表示继续执行
    """
    # 1. 先检查内存标记
    if STOP_FLAGS.get(task_id):
        return True
    
    # 2. 再检查 Redis 标记（分布式场景）
    try:
        stop_flag = redis.get(f"stop:{task_id}")
        if stop_flag:
            STOP_FLAGS[task_id] = True  # 同步到内存
            return True
    except Exception as e:
        print(f"⚠️ 检查取消标记失败：{e}")
    
    return False


def set_stop_flag(task_id: str):
    """
    设置任务取消标记
    
    参数:
        task_id: 任务 ID
    """
    STOP_FLAGS[task_id] = True
    try:
        redis.set(f"stop:{task_id}", "1")
    except Exception as e:
        print(f"⚠️ 设置取消标记失败：{e}")


def clear_stop_flag(task_id: str):
    """
    清理任务取消标记（任务完成后调用）
    
    参数:
        task_id: 任务 ID
    """
    if task_id in STOP_FLAGS:
        del STOP_FLAGS[task_id]
    try:
        redis.delete(f"stop:{task_id}")
    except Exception as e:
        print(f"⚠️ 清理取消标记失败：{e}")

# =========================
# 流式输出（Emitter）
# =========================

def stream_start(task_id: str, title: str = "Qwen 正在生成..."):
    try:
        requests.post(
            f"{NODE_API_URL}/task/stream_start/{task_id}",
            json={"task_id": task_id, "title": title},
            timeout=5,
        )
    except Exception as e:
        print(f"⚠️ stream_start 失败：{e}")


def stream_chunk(task_id: str, content: str):
    try:
        requests.post(
            f"{NODE_API_URL}/task/stream_chunk/{task_id}",
            json={"task_id": task_id, "content": content},
            timeout=5,
        )
    except Exception as e:
        print(f"⚠️ stream_chunk 失败：{e}")


def stream_error(task_id: str, message: str):
    try:
        requests.post(
            f"{NODE_API_URL}/task/stream_error/{task_id}",
            json={"task_id": task_id, "message": message},
            timeout=5,
        )
    except Exception as e:
        print(f"⚠️ stream_error 失败：{e}")


def stream_end(task_id: str):
    try:
        requests.post(
            f"{NODE_API_URL}/task/stream_end/{task_id}",
            json={"task_id": task_id},
            timeout=5,
        )
    except Exception as e:
        print(f"⚠️ stream_end 失败：{e}")


# =========================
# 上下文结构（context）
# =========================

def create_empty_context():
    return {
        "memory": {},
        "intermediate_results": [],
        "tool_outputs": [],
        "subtasks": []
    }


# =========================
# 事件结构
# =========================

def create_event(event_type: str, data: dict):
    return {
        "timestamp": int(time.time() * 1000),
        "type": event_type,
        "data": data or {}
    }