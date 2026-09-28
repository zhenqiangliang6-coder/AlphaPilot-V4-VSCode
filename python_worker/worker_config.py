# -*- coding: utf-8 -*-
# worker_config.py
# ---------------------------------------------------------
# Worker 基础配置、Redis、流式输出、上下文结构
# - ⭐ v2.8 双云 Redis 架构（Upstash + 阿里云 Tair）
# - 根据模型类型自动选择最优 Redis 实例
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
# ⭐ v2.8 新增：内存模式开关（用于调试）
# =========================

USE_MEMORY_REDIS = os.getenv("USE_MEMORY_REDIS", "false").lower() == "true"

# =========================
# ⭐ v2.8 新增：双云 Redis 配置
# =========================

# Redis 类型选择：upstash | tair | memory | auto
# - auto: 根据模型类型自动选择（推荐）
# - upstash: 强制使用 Upstash（国际模型）
# - tair: 强制使用阿里云 Tair（国内模型）
# - memory: 内存模式（调试用）
REDIS_TYPE = os.getenv("REDIS_TYPE", "auto").lower()

# 国内模型列表（使用阿里云 Tair）
# ✅ DeepSeek 和 Doubao 已恢复至国内模型列表，使用阿里云 Tair Redis
DOMESTIC_MODELS = [
    "deepseek",
    "doubao",
    "ernie",
    "glm",
]

# 国际模型列表（使用 Upstash）
INTERNATIONAL_MODELS = [
    "openai",
    "claude",
    "gemini",
    "llama",
    "qwen",  # ✅ Qwen 归类为国际模型，使用 Upstash
]


def get_redis_type_for_model(model_name: str = None) -> str:
    """
    根据模型名称确定应该使用的 Redis 类型
    
    参数:
        model_name: 模型名称（如 "deepseek_generate", "qwen_write"）
    
    返回:
        str: Redis 类型 ("upstash" | "tair" | "memory")
    """
    if USE_MEMORY_REDIS:
        return "memory"
    
    # 如果强制指定了类型，直接使用
    if REDIS_TYPE != "auto":
        return REDIS_TYPE
    
    # 自动模式：根据模型名称判断
    if not model_name:
        # 如果没有提供模型名称，默认使用 Upstash
        return "upstash"
    
    model_lower = model_name.lower()
    
    # 检查是否是国内模型
    for domestic in DOMESTIC_MODELS:
        if domestic in model_lower:
            return "tair"
    
    # 默认使用 Upstash（国际模型）
    return "upstash"


def create_redis_client(redis_type: str = None, model_name: str = None):
    """
    创建 Redis 客户端（支持多种后端）
    
    参数:
        redis_type: Redis 类型 (upstash | tair | memory)
                   如果为 None，则根据 model_name 自动判断
        model_name: 模型名称（用于自动判断 Redis 类型）
    
    返回:
        Redis 客户端实例
    """
    # 确定 Redis 类型
    if redis_type is None:
        redis_type = get_redis_type_for_model(model_name)
    
    # 1. 内存模式（调试用）
    if redis_type == "memory":
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
                str_values = [str(v) for v in values]
                self.data[key] = str_values + self.data[key]
                return len(self.data[key])
            
            def rpop(self, key):
                if key in self.data and self.data[key]:
                    return self.data[key].pop()
                return None
            
            def llen(self, key):
                return len(self.data.get(key, []))
        
        return MemoryRedis()
    
    # 2. Upstash Redis（国际模型）
    elif redis_type == "upstash":
        print("✅ 使用 Upstash Redis（国际模型/全球 CDN）")
        from upstash_redis import Redis
        
        upstash_url = os.getenv("UPSTASH_REDIS_REST_URL")
        upstash_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
        
        if not upstash_url or not upstash_token:
            raise ValueError("UPSTASH_REDIS_REST_URL 和 UPSTASH_REDIS_REST_TOKEN 必须设置")
        
        return Redis(url=upstash_url, token=upstash_token)
    
    # 3. 阿里云 Tair Redis（国内模型）
    elif redis_type == "tair":
        print("✅ 使用阿里云 Tair Redis（国内模型/国内加速）")
        import redis as redis_py
        
        tair_host = os.getenv("TAIR_HOST")
        tair_port = int(os.getenv("TAIR_PORT", "6379"))
        tair_password = os.getenv("TAIR_PASSWORD")
        tair_tls = os.getenv("TAIR_TLS", "true").lower() == "true"
        
        if not tair_host or not tair_password:
            raise ValueError("TAIR_HOST 和 TAIR_PASSWORD 必须设置")
        
        # 构造连接参数
        connection_params = {
            'host': tair_host,
            'port': tair_port,
            'password': tair_password,
            'decode_responses': True,  # 自动解码为字符串
            'socket_timeout': 10,
            'socket_connect_timeout': 10,
        }
        
        # 如果启用 TLS
        if tair_tls:
            import ssl
            connection_params['ssl'] = True
            connection_params['ssl_cert_reqs'] = ssl.CERT_NONE  # 跳过证书验证（生产环境应配置证书）
        
        return redis_py.Redis(**connection_params)
    
    else:
        raise ValueError(f"不支持的 Redis 类型: {redis_type}")


# =========================
# 基础配置
# =========================

# ⭐ v2.8: 延迟初始化 Redis 客户端（根据 Worker 类型动态选择）
# 不再在模块加载时创建，而是通过 get_redis_client() 函数按需创建

def get_worker_model_type():
    """
    根据 WORKER_ID 推断模型类型
    
    返回:
        str: 模型类型 ("qwen" | "deepseek" | "doubao" | "openai" | "local" | ...)
    """
    worker_id = os.getenv("WORKER_ID", "").lower()
    
    if "qwen" in worker_id:
        return "qwen"
    elif "deepseek" in worker_id:
        return "deepseek"
    elif "doubao" in worker_id:
        return "doubao"
    elif "claude" in worker_id:
        return "claude"
    elif "gemini" in worker_id:
        return "gemini"
    elif "openai" in worker_id:
        return "openai"
    elif "local" in worker_id:
        return "local"
    else:
        # 默认使用 qwen
        return "qwen"


# ⭐ 全局 Redis 客户端（延迟初始化）
_redis_client = None

def get_redis_client():
    """
    获取 Redis 客户端（单例模式，延迟初始化）
    
    根据 WORKER_ID 自动选择最优的 Redis 实例：
    - Qwen → Upstash（国际稳定）
    - DeepSeek/Doubao → 阿里云 Tair（国内加速）
    - 其他国际模型 → Upstash
    
    返回:
        Redis 客户端实例
    """
    global _redis_client
    
    if _redis_client is not None:
        return _redis_client
    
    # 根据 Worker ID 推断模型类型
    model_type = get_worker_model_type()
    
    # 创建对应的 Redis 客户端
    _redis_client = create_redis_client(model_name=f"{model_type}_worker")
    
    print(f"💡 Worker 类型: {model_type}")
    print(f"💡 Redis 类型: {get_redis_type_for_model(f'{model_type}_worker')}")
    
    return _redis_client


# ⭐ 为了向后兼容，提供 redis 变量（但建议使用 get_redis_client()）
# 注意：这会在首次调用 get_redis_client() 时初始化
class _LazyRedis:
    """延迟加载的 Redis 代理"""
    def __getattr__(self, name):
        client = get_redis_client()
        return getattr(client, name)

redis = _LazyRedis()

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
    "local": "task_queue:local",  # ⭐ Local LLM Worker
    "maas": "task_queue:maas",  # ⭐ 腾讯 MaaS (TokenHub)
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

def stream_start(task_id: str, title: str = "Qwen 正在生成...", phase: str = None):
    try:
        payload = {"task_id": task_id, "title": title}
        if phase is not None:
            payload["phase"] = phase
        requests.post(
            f"{NODE_API_URL}/task/stream_start/{task_id}",
            json=payload,
            timeout=5,
        )
    except Exception as e:
        print(f"⚠️ stream_start 失败：{e}")


def stream_chunk(task_id: str, content: str, phase: str = None, channel: str = None):
    try:
        payload = {"task_id": task_id, "content": content}
        if phase is not None:
            payload["phase"] = phase
        if channel is not None:
            payload["channel"] = channel
        requests.post(
            f"{NODE_API_URL}/task/stream_chunk/{task_id}",
            json=payload,
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