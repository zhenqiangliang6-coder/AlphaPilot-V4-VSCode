# -*- coding: utf-8 -*-
"""
monitor_workers.py
---------------------------------------------------------
多 Worker 监控工具

功能：
1. 实时显示队列长度
2. 显示活跃的 Worker 数量
3. 监控任务分配情况

使用方法：
    python monitor_workers.py
"""

import os
import time
import json
from dotenv import load_dotenv
from upstash_redis import Redis

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

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def monitor_workers():
    """监控多 Worker 状态"""
    
    # 初始化 Redis
    redis = Redis(
        url=os.getenv("UPSTASH_REDIS_REST_URL"),
        token=os.getenv("UPSTASH_REDIS_REST_TOKEN")
    )
    
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}AlphaPilot 多 Worker 监控工具{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}\n")
    
    # 要监控的队列
    queues = [
        "task_queue:qwen",
        "task_queue:deepseek",
        "task_queue:doubao",
    ]
    
    try:
        while True:
            clear_screen()
            
            print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
            print(f"{Colors.BOLD}{Colors.CYAN}Worker 监控面板 (按 Ctrl+C 退出){Colors.RESET}")
            print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}\n")
            
            # 显示当前时间
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"{Colors.BLUE}⏰ 当前时间: {current_time}{Colors.RESET}\n")
            
            # 监控每个队列
            for queue_name in queues:
                queue_length = redis.llen(queue_name)
                
                # 根据队列长度设置颜色
                if queue_length == 0:
                    color = Colors.GREEN
                    status = "空闲"
                elif queue_length < 5:
                    color = Colors.YELLOW
                    status = "少量任务"
                else:
                    color = Colors.RED
                    status = f"积压 ({queue_length} 个任务)"
                
                print(f"{Colors.BOLD}📊 队列: {queue_name}{Colors.RESET}")
                print(f"   状态: {color}{status}{Colors.RESET}")
                print(f"   待处理任务数: {queue_length}\n")
            
            # 显示活跃的 Worker（通过检查 stop flag 键）
            print(f"{Colors.BOLD}👥 活跃的 Worker:{Colors.RESET}")
            
            # 扫描可能的 Worker ID
            worker_ids = []
            for i in range(1, 10):
                for model in ["qwen", "deepseek", "doubao"]:
                    worker_id = f"{model}-worker-{i}"
                    # 检查是否有相关的键
                    keys = redis.keys(f"*{worker_id}*")
                    if keys:
                        worker_ids.append(worker_id)
            
            if worker_ids:
                for wid in set(worker_ids):  # 去重
                    print(f"   {Colors.GREEN}✅ {wid}{Colors.RESET}")
            else:
                print(f"   {Colors.YELLOW}⚠️  未检测到活跃的 Worker{Colors.RESET}")
            
            print(f"\n{Colors.CYAN}💡 提示:{Colors.RESET}")
            print(f"   - 启动 Worker: $env:WORKER_ID='qwen-worker-1'; python -m python_worker.agents.qwen.qwen_worker_v2")
            print(f"   - 提交任务后观察队列变化")
            print(f"   - 多个 Worker 会自动负载均衡\n")
            
            # 等待 2 秒后刷新
            time.sleep(2)
            
    except KeyboardInterrupt:
        print(f"\n\n{Colors.GREEN}👋 监控已停止{Colors.RESET}")
    except Exception as e:
        print(f"\n{Colors.RED}❌ 错误: {e}{Colors.RESET}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    monitor_workers()
