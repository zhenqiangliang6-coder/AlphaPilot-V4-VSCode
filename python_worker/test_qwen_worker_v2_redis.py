# -*- coding: utf-8 -*-
"""
test_qwen_worker_v2_redis.py
---------------------------------------------------------
Qwen Worker v2 Redis 连接诊断测试脚本

功能：
1. 测试 Upstash Redis 连接（检测网络/代理问题）
2. 支持切换到内存模式进行对比测试
3. 详细输出每个步骤的状态和错误信息

使用方法：
    # 测试云 Redis（默认）
    python test_qwen_worker_v2_redis.py
    
    # 测试内存模式
    python test_qwen_worker_v2_redis.py --use-memory
    
    # 详细日志模式
    python test_qwen_worker_v2_redis.py --verbose
"""

import os
import sys
import time
import json
import argparse
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# =========================
# 配置参数
# =========================

# ⭐ 关键开关：是否使用内存模式（绕过云 Redis）
USE_MEMORY_MODE = False  # 默认使用云 Redis，可通过命令行参数覆盖

# 详细日志开关
VERBOSE = False

# =========================
# 颜色输出工具
# =========================

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_success(msg):
    print(f"{Colors.GREEN}✅ {msg}{Colors.RESET}")

def print_error(msg):
    print(f"{Colors.RED}❌ {msg}{Colors.RESET}")

def print_warning(msg):
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.RESET}")

def print_info(msg):
    print(f"{Colors.BLUE}ℹ️  {msg}{Colors.RESET}")

def print_section(title):
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{title}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}\n")

def print_verbose(msg):
    if VERBOSE:
        print(f"  {Colors.CYAN}📝 {msg}{Colors.RESET}")

# =========================
# 测试 1: 环境变量检查
# =========================

def test_environment_variables():
    """检查必要的环境变量是否配置"""
    print_section("测试 1: 环境变量检查")
    
    required_vars = [
        "UPSTASH_REDIS_REST_URL",
        "UPSTASH_REDIS_REST_TOKEN",
        "DASHSCOPE_API_KEY",
        "WORKER_ID"
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if value:
            if "KEY" in var or "TOKEN" in var:
                # 隐藏敏感信息
                masked = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
                print_success(f"{var}: {masked}")
            else:
                print_success(f"{var}: {value}")
        else:
            print_error(f"{var}: 未设置")
            missing_vars.append(var)
    
    if missing_vars:
        print_error(f"缺少以下环境变量: {', '.join(missing_vars)}")
        return False
    
    return True

# =========================
# 测试 2: Upstash Redis 连接测试
# =========================

def test_upstash_redis_connection():
    """测试 Upstash Redis REST API 连接"""
    print_section("测试 2: Upstash Redis 连接测试")
    
    redis_url = os.getenv("UPSTASH_REDIS_REST_URL")
    redis_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
    
    print_info(f"Redis URL: {redis_url}")
    print_info(f"Redis Token: {redis_token[:8]}...{redis_token[-4:]}")
    
    try:
        import requests
        
        # 测试 1: PING 命令
        print("\n🔍 测试 1: PING 命令")
        response = requests.post(
            f"{redis_url}/ping",
            headers={"Authorization": f"Bearer {redis_token}"},
            timeout=10
        )
        
        if response.status_code == 200:
            print_success(f"PING 成功: {response.text}")
        else:
            print_error(f"PING 失败: HTTP {response.status_code} - {response.text}")
            return False
        
        # 测试 2: SET/GET 命令
        print("\n🔍 测试 2: SET/GET 命令")
        test_key = f"test:{int(time.time())}"
        test_value = "hello_from_test"
        
        # SET
        set_response = requests.post(
            f"{redis_url}/set/{test_key}/{test_value}",
            headers={"Authorization": f"Bearer {redis_token}"},
            timeout=10
        )
        
        if set_response.status_code == 200:
            print_success(f"SET 成功: {set_response.text}")
        else:
            print_error(f"SET 失败: HTTP {set_response.status_code} - {set_response.text}")
            return False
        
        # GET
        get_response = requests.get(
            f"{redis_url}/get/{test_key}",
            headers={"Authorization": f"Bearer {redis_token}"},
            timeout=10
        )
        
        if get_response.status_code == 200:
            retrieved_value = get_response.json().get("result")
            if retrieved_value == test_value:
                print_success(f"GET 成功: 值匹配 ({retrieved_value})")
            else:
                print_error(f"GET 失败: 值不匹配 (期望: {test_value}, 实际: {retrieved_value})")
                return False
        else:
            print_error(f"GET 失败: HTTP {get_response.status_code} - {get_response.text}")
            return False
        
        # 清理测试数据
        requests.post(
            f"{redis_url}/del/{test_key}",
            headers={"Authorization": f"Bearer {redis_token}"},
            timeout=5
        )
        
        print_success("Upstash Redis 连接正常！")
        return True
        
    except requests.exceptions.Timeout:
        print_error("连接超时：可能是网络问题或代理配置问题")
        print_warning("建议：")
        print_warning("  1. 检查网络连接")
        print_warning("  2. 检查是否需要配置代理")
        print_warning("  3. 尝试切换到内存模式进行测试")
        return False
        
    except requests.exceptions.ConnectionError as e:
        print_error(f"连接错误: {e}")
        print_warning("可能的原因：")
        print_warning("  1. DNS 解析失败")
        print_warning("  2. 防火墙阻止连接")
        print_warning("  3. 代理配置不正确")
        return False
        
    except Exception as e:
        print_error(f"未知错误: {type(e).__name__}: {e}")
        return False

# =========================
# 测试 3: Python SDK 连接测试
# =========================

def test_python_sdk_connection():
    """测试 upstash-redis Python SDK 连接"""
    print_section("测试 3: Python SDK 连接测试")
    
    try:
        from upstash_redis import Redis
        
        redis_url = os.getenv("UPSTASH_REDIS_REST_URL")
        redis_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
        
        print_info("初始化 Redis 客户端...")
        redis_client = Redis(url=redis_url, token=redis_token)
        
        # 测试 PING
        print("\n🔍 测试 PING...")
        result = redis_client.ping()
        if result:
            print_success(f"PING 成功: {result}")
        else:
            print_error("PING 返回 False")
            return False
        
        # 测试 SET/GET
        print("\n🔍 测试 SET/GET...")
        test_key = f"sdk_test:{int(time.time())}"
        test_value = "sdk_hello"
        
        redis_client.set(test_key, test_value)
        retrieved = redis_client.get(test_key)
        
        if retrieved == test_value:
            print_success(f"SET/GET 成功: 值匹配 ({retrieved})")
        else:
            print_error(f"SET/GET 失败: 值不匹配 (期望: {test_value}, 实际: {retrieved})")
            return False
        
        # 清理
        redis_client.delete(test_key)
        
        print_success("Python SDK 连接正常！")
        return True
        
    except ImportError:
        print_error("upstash-redis 库未安装")
        print_warning("请运行: pip install upstash-redis")
        return False
        
    except Exception as e:
        print_error(f"SDK 连接失败: {type(e).__name__}: {e}")
        import traceback
        if VERBOSE:
            print_verbose(traceback.format_exc())
        return False

# =========================
# 测试 4: 内存模式模拟
# =========================

class MemoryRedis:
    """内存 Redis 模拟器（用于测试）"""
    
    def __init__(self):
        self.data = {}
        print_info("使用内存模式（绕过云 Redis）")
    
    def ping(self):
        return True
    
    def set(self, key, value):
        self.data[key] = value
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
        self.data[key] = list(values) + self.data[key]
        return len(self.data[key])
    
    def rpop(self, key):
        if key in self.data and self.data[key]:
            return self.data[key].pop()
        return None
    
    def llen(self, key):
        return len(self.data.get(key, []))

def test_memory_mode():
    """测试内存模式"""
    print_section("测试 4: 内存模式测试")
    
    try:
        redis_mock = MemoryRedis()
        
        # 测试 PING
        print("\n🔍 测试 PING...")
        if redis_mock.ping():
            print_success("PING 成功")
        else:
            print_error("PING 失败")
            return False
        
        # 测试 SET/GET
        print("\n🔍 测试 SET/GET...")
        redis_mock.set("test_key", "test_value")
        result = redis_mock.get("test_key")
        if result == "test_value":
            print_success(f"SET/GET 成功: {result}")
        else:
            print_error(f"SET/GET 失败: {result}")
            return False
        
        # 测试队列操作
        print("\n🔍 测试队列操作...")
        redis_mock.lpush("task_queue:qwen", json.dumps({"test": "task"}))
        length = redis_mock.llen("task_queue:qwen")
        if length > 0:
            print_success(f"队列推送成功，当前长度: {length}")
            task = redis_mock.rpop("task_queue:qwen")
            if task:
                print_success(f"队列弹出成功: {task}")
            else:
                print_error("队列弹出失败")
                return False
        else:
            print_error("队列推送失败")
            return False
        
        print_success("内存模式工作正常！")
        return True
        
    except Exception as e:
        print_error(f"内存模式测试失败: {type(e).__name__}: {e}")
        import traceback
        if VERBOSE:
            print_verbose(traceback.format_exc())
        return False

# =========================
# 测试 5: Qwen Worker 初始化测试
# =========================

def test_worker_initialization(use_memory=False):
    """测试 Worker 初始化流程"""
    print_section("测试 5: Worker 初始化测试")
    
    try:
        # 根据模式选择 Redis 客户端
        if use_memory:
            print_info("使用内存模式初始化 Worker...")
            redis_client = MemoryRedis()
        else:
            print_info("使用云 Redis 初始化 Worker...")
            from upstash_redis import Redis
            redis_client = Redis(
                url=os.getenv("UPSTASH_REDIS_REST_URL"),
                token=os.getenv("UPSTASH_REDIS_REST_TOKEN")
            )
        
        # 测试基本操作
        print("\n🔍 测试队列监听...")
        queue_name = "task_queue:qwen"
        
        # 推送一个测试任务
        test_task = {
            "task_id": f"test_{int(time.time())}",
            "task_type": "qwen_generate",
            "payload": {"prompt": "测试任务"},
            "steps": [],
            "events": [],
            "context": {}
        }
        
        redis_client.lpush(queue_name, json.dumps(test_task))
        print_success(f"测试任务已推送到队列: {queue_name}")
        
        # 检查队列长度
        length = redis_client.llen(queue_name)
        print_success(f"队列当前长度: {length}")
        
        # 弹出任务
        task_data = redis_client.rpop(queue_name)
        if task_data:
            task = json.loads(task_data)
            print_success(f"成功从队列获取任务: {task['task_id']}")
        else:
            print_error("从队列获取任务失败")
            return False
        
        print_success("Worker 初始化流程正常！")
        return True
        
    except Exception as e:
        print_error(f"Worker 初始化失败: {type(e).__name__}: {e}")
        import traceback
        if VERBOSE:
            print_verbose(traceback.format_exc())
        return False

# =========================
# 主测试流程
# =========================

def main():
    """主测试函数"""
    global USE_MEMORY_MODE, VERBOSE
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="Qwen Worker v2 Redis 连接诊断工具")
    parser.add_argument("--use-memory", action="store_true", help="使用内存模式（绕过云 Redis）")
    parser.add_argument("--verbose", action="store_true", help="显示详细日志")
    args = parser.parse_args()
    
    USE_MEMORY_MODE = args.use_memory
    VERBOSE = args.verbose
    
    print_section("Qwen Worker v2 Redis 连接诊断工具")
    print_info(f"运行模式: {'内存模式' if USE_MEMORY_MODE else '云 Redis 模式'}")
    print_info(f"详细日志: {'开启' if VERBOSE else '关闭'}")
    
    results = {}
    
    # 测试 1: 环境变量
    results["环境变量"] = test_environment_variables()
    
    if not USE_MEMORY_MODE:
        # 测试 2: Upstash REST API
        results["Upstash REST API"] = test_upstash_redis_connection()
        
        # 测试 3: Python SDK
        results["Python SDK"] = test_python_sdk_connection()
    
    # 测试 4: 内存模式（总是测试）
    results["内存模式"] = test_memory_mode()
    
    # 测试 5: Worker 初始化
    mode_name = "内存" if USE_MEMORY_MODE else "云 Redis"
    results[f"Worker 初始化 ({mode_name})"] = test_worker_initialization(use_memory=USE_MEMORY_MODE)
    
    # 总结
    print_section("测试结果总结")
    
    all_passed = True
    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        color = Colors.GREEN if passed else Colors.RED
        print(f"{color}{test_name}: {status}{Colors.RESET}")
        if not passed:
            all_passed = False
    
    print(f"\n{'='*60}")
    if all_passed:
        print_success("所有测试通过！✨")
        if USE_MEMORY_MODE:
            print_info("💡 提示: 内存模式工作正常，如果云 Redis 失败，可能是网络/代理问题")
    else:
        print_error("部分测试失败，请检查上述错误信息")
        print_warning("\n排查建议:")
        if not results.get("Upstash REST API") or not results.get("Python SDK"):
            print_warning("  1. 检查网络连接和代理配置")
            print_warning("  2. 尝试运行: python test_qwen_worker_v2_redis.py --use-memory")
            print_warning("  3. 检查 Upstash Redis URL 和 Token 是否正确")
        if not results.get("环境变量"):
            print_warning("  4. 检查 .env 文件配置")
    
    print(f"{'='*60}\n")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
