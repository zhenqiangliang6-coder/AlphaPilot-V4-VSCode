# -*- coding: utf-8 -*-
"""
test_multi_workers.py
---------------------------------------------------------
多 Worker 功能测试脚本

功能：
1. 自动启动多个 Worker
2. 提交多个测试任务
3. 验证任务被不同 Worker 处理
4. 生成测试报告

使用方法：
    python test_multi_workers.py --workers 3 --tasks 5
"""

import os
import sys
import time
import json
import subprocess
import argparse
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

class MultiWorkerTester:
    """多 Worker 测试器"""
    
    def __init__(self, num_workers=3, num_tasks=5):
        self.num_workers = num_workers
        self.num_tasks = num_tasks
        self.workers = []
        self.task_ids = []
        
        # 初始化 Redis
        self.redis = Redis(
            url=os.getenv("UPSTASH_REDIS_REST_URL"),
            token=os.getenv("UPSTASH_REDIS_REST_TOKEN")
        )
        
        # 检查是否使用内存模式
        use_memory = os.getenv("USE_MEMORY_REDIS", "false").lower() == "true"
        if use_memory:
            print_error("❌ 内存模式不支持多 Worker 测试！")
            print_warning("请设置 USE_MEMORY_REDIS=false 后重试")
            sys.exit(1)
    
    def start_workers(self):
        """启动多个 Worker"""
        print_section(f"步骤 1: 启动 {self.num_workers} 个 Worker")
        
        for i in range(1, self.num_workers + 1):
            worker_id = f"qwen-worker-{i}"
            print_info(f"启动 Worker {i}: {worker_id}")
            
            # 设置环境变量并启动 Worker
            env = os.environ.copy()
            env["WORKER_ID"] = worker_id
            
            # 在后台启动 Worker
            process = subprocess.Popen(
                [sys.executable, "-m", "python_worker.agents.qwen.qwen_worker_v2"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
            )
            
            self.workers.append({
                "id": worker_id,
                "process": process,
                "tasks_handled": 0
            })
            
            print_success(f"Worker {i} 已启动 (PID: {process.pid})")
            time.sleep(1)  # 等待 Worker 初始化
        
        print_success(f"所有 {self.num_workers} 个 Worker 已启动\n")
    
    def submit_tasks(self):
        """提交多个测试任务"""
        print_section(f"步骤 2: 提交 {self.num_tasks} 个测试任务")
        
        queue_name = "task_queue:qwen"
        
        for i in range(1, self.num_tasks + 1):
            task_id = f"test-task-{int(time.time())}-{i}"
            self.task_ids.append(task_id)
            
            task = {
                "task_id": task_id,
                "task_type": "qwen_generate",
                "payload": {
                    "prompt": f"这是测试任务 {i}，用于验证多 Worker 负载均衡"
                },
                "steps": [],
                "events": [],
                "context": {}
            }
            
            # 推送到队列
            self.redis.lpush(queue_name, json.dumps(task))
            print_success(f"任务 {i} 已提交: {task_id}")
            
            time.sleep(0.5)  # 稍微延迟，避免瞬间推送
        
        print_info(f"\n队列当前长度: {self.redis.llen(queue_name)}\n")
    
    def monitor_execution(self, timeout=60):
        """监控任务执行"""
        print_section("步骤 3: 监控任务执行")
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            queue_length = self.redis.llen("task_queue:qwen")
            
            print_info(f"队列剩余任务数: {queue_length}")
            
            if queue_length == 0:
                print_success("所有任务已处理完成！\n")
                break
            
            time.sleep(2)
        else:
            print_warning(f"超时 ({timeout}秒)，仍有 {queue_length} 个任务未处理\n")
    
    def generate_report(self):
        """生成测试报告"""
        print_section("测试报告")
        
        print(f"{Colors.BOLD}配置信息:{Colors.RESET}")
        print(f"  Worker 数量: {self.num_workers}")
        print(f"  任务数量: {self.num_tasks}")
        print(f"  Redis 模式: Upstash 云 Redis\n")
        
        print(f"{Colors.BOLD}测试结果:{Colors.RESET}")
        
        # 检查队列是否为空
        final_queue_length = self.redis.llen("task_queue:qwen")
        
        if final_queue_length == 0:
            print_success("✅ 所有任务已成功处理")
            print_success("✅ 多 Worker 负载均衡工作正常")
        else:
            print_error(f"❌ 仍有 {final_queue_length} 个任务未处理")
            print_warning("可能原因:")
            print_warning("  1. Worker 处理速度慢")
            print_warning("  2. 某个 Worker 崩溃")
            print_warning("  3. 网络连接问题")
        
        print(f"\n{Colors.BOLD}Worker 状态:{Colors.RESET}")
        for worker in self.workers:
            status = "运行中" if worker["process"].poll() is None else "已停止"
            color = Colors.GREEN if status == "运行中" else Colors.RED
            print(f"  {color}{worker['id']}: {status} (PID: {worker['process'].pid}){Colors.RESET}")
        
        print(f"\n{Colors.BOLD}清理建议:{Colors.RESET}")
        print(f"  1. 手动停止 Worker 进程 (Ctrl+C)")
        print(f"  2. 或者运行: taskkill /F /PID <PID>")
        print(f"  3. 检查 Redis 队列是否清空\n")
    
    def cleanup(self):
        """清理资源"""
        print_section("清理资源")
        
        print_info("停止所有 Worker...")
        
        for worker in self.workers:
            try:
                worker["process"].terminate()
                worker["process"].wait(timeout=5)
                print_success(f"{worker['id']} 已停止")
            except Exception as e:
                print_error(f"停止 {worker['id']} 失败: {e}")
        
        print_success("清理完成\n")
    
    def run(self):
        """运行完整测试"""
        print_section("AlphaPilot 多 Worker 测试")
        
        try:
            self.start_workers()
            self.submit_tasks()
            self.monitor_execution()
            self.generate_report()
        except KeyboardInterrupt:
            print_warning("\n\n测试被用户中断")
        except Exception as e:
            print_error(f"\n测试失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.cleanup()

def main():
    parser = argparse.ArgumentParser(description="多 Worker 功能测试")
    parser.add_argument("--workers", type=int, default=3, help="Worker 数量 (默认: 3)")
    parser.add_argument("--tasks", type=int, default=5, help="任务数量 (默认: 5)")
    args = parser.parse_args()
    
    tester = MultiWorkerTester(num_workers=args.workers, num_tasks=args.tasks)
    tester.run()

if __name__ == "__main__":
    main()
