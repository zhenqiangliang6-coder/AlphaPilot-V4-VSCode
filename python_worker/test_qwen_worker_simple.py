# -*- coding: utf-8 -*-
"""
test_qwen_worker_simple.py
---------------------------------------------------------
Qwen Worker 简单测试脚本

功能：
1. 检查环境配置
2. 测试 Redis 连接
3. 提交一个测试任务
4. 等待并显示结果

使用方法：
    python test_qwen_worker_simple.py
"""

import os
import sys
import time
import json
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 颜色输出
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_section(title):
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{title}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}\n")

def print_success(msg):
    print(f"{Colors.GREEN}✅ {msg}{Colors.RESET}")

def print_error(msg):
    print(f"{Colors.RED}❌ {msg}{Colors.RESET}")

def print_info(msg):
    print(f"{Colors.BLUE}ℹ️  {msg}{Colors.RESET}")

def print_warning(msg):
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.RESET}")

def check_environment():
    """检查环境配置"""
    print_section("步骤 1: 检查环境配置")
    
    required_vars = {
        "UPSTASH_REDIS_REST_URL": "Redis URL",
        "UPSTASH_REDIS_REST_TOKEN": "Redis Token",
        "DASHSCOPE_API_KEY": "通义千问 API Key",
    }
    
    all_ok = True
    for var, desc in required_vars.items():
        value = os.getenv(var)
        if value:
            if "TOKEN" in var or "KEY" in var:
                masked = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
                print_success(f"{desc}: {masked}")
            else:
                print_success(f"{desc}: {value}")
        else:
            print_error(f"{desc}: 未设置")
            all_ok = False
    
    # 检查内存模式
    use_memory = os.getenv("USE_MEMORY_REDIS", "false").lower() == "true"
    if use_memory:
        print_warning("当前使用内存模式（不支持多 Worker）")
    else:
        print_success("当前使用云 Redis 模式")
    
    return all_ok

def test_redis_connection():
    """测试 Redis 连接"""
    print_section("步骤 2: 测试 Redis 连接")
    
    try:
        from upstash_redis import Redis
        
        redis = Redis(
            url=os.getenv("UPSTASH_REDIS_REST_URL"),
            token=os.getenv("UPSTASH_REDIS_REST_TOKEN")
        )
        
        # 测试 PING
        result = redis.ping()
        if result:
            print_success(f"Redis 连接成功: {result}")
        else:
            print_error("Redis PING 失败")
            return None
        
        # 测试 SET/GET
        test_key = f"test:{int(time.time())}"
        redis.set(test_key, "hello")
        value = redis.get(test_key)
        
        if value == "hello":
            print_success("Redis SET/GET 测试通过")
        else:
            print_error("Redis SET/GET 测试失败")
            return None
        
        # 清理
        redis.delete(test_key)
        
        return redis
        
    except ImportError:
        print_error("upstash-redis 库未安装")
        print_info("请运行: pip install upstash-redis")
        return None
    except Exception as e:
        print_error(f"Redis 连接失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def submit_test_task(redis):
    """提交测试任务"""
    print_section("步骤 3: 提交测试任务")
    
    queue_name = "task_queue:qwen"
    task_id = f"simple-test-{int(time.time())}"
    
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
    
    try:
        redis.lpush(queue_name, json.dumps(task))
        print_success(f"任务已提交到队列: {queue_name}")
        print_info(f"任务 ID: {task_id}")
        print_info(f"队列当前长度: {redis.llen(queue_name)}")
        
        return task_id
        
    except Exception as e:
        print_error(f"提交任务失败: {e}")
        return None

def wait_for_result(redis, task_id, timeout=120):
    """等待任务结果"""
    print_section("步骤 4: 等待任务结果")
    
    result_key = f"task_result:{task_id}"
    start_time = time.time()
    
    print_info(f"等待任务完成... (超时: {timeout}秒)")
    print_info("提示: 确保 qwen-worker 正在运行\n")
    
    while time.time() - start_time < timeout:
        # 检查结果
        result = redis.get(result_key)
        
        if result:
            try:
                result_data = json.loads(result)
                print_success("任务完成！")
                print_info(f"结果: {json.dumps(result_data, indent=2, ensure_ascii=False)}")
                return True
            except Exception as e:
                print_error(f"解析结果失败: {e}")
                print_info(f"原始数据: {result}")
                return False
        
        # 检查是否失败
        error_key = f"task_error:{task_id}"
        error = redis.get(error_key)
        if error:
            print_error(f"任务失败: {error}")
            return False
        
        # 显示等待状态
        elapsed = int(time.time() - start_time)
        print(f"  ⏳ 已等待 {elapsed} 秒...", end='\r')
        
        time.sleep(2)
    
    print_error(f"\n超时 ({timeout}秒)，未收到结果")
    print_warning("可能原因:")
    print_warning("  1. qwen-worker 未启动")
    print_warning("  2. Worker 处理速度慢")
    print_warning("  3. 网络连接问题")
    print_warning("  4. API Key 无效")
    
    return False

def main():
    """主测试流程"""
    print_section("Qwen Worker 简单测试")
    
    # 步骤 1: 检查环境
    if not check_environment():
        print_error("\n环境配置不完整，请检查 .env 文件")
        return 1
    
    # 步骤 2: 测试 Redis
    redis = test_redis_connection()
    if not redis:
        print_error("\nRedis 连接失败，无法继续测试")
        return 1
    
    # 步骤 3: 提交任务
    task_id = submit_test_task(redis)
    if not task_id:
        print_error("\n任务提交失败")
        return 1
    
    # 步骤 4: 等待结果
    success = wait_for_result(redis, task_id, timeout=120)
    
    # 总结
    print_section("测试总结")
    
    if success:
        print_success("🎉 所有测试通过！")
        print_success("qwen-worker 工作正常")
        print_info("\n下一步:")
        print_info("  1. 在 VSCode 中使用 AlphaPilot 扩展")
        print_info("  2. 或运行多 Worker 测试: python test_multi_workers.py")
        return 0
    else:
        print_error("❌ 测试失败")
        print_warning("\n排查建议:")
        print_warning("  1. 确保 qwen-worker 正在运行")
        print_warning("  2. 检查 Worker 日志是否有错误")
        print_warning("  3. 验证 DASHSCOPE_API_KEY 是否有效")
        print_warning("  4. 尝试增加超时时间")
        return 1

if __name__ == "__main__":
    sys.exit(main())
