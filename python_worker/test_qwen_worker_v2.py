# -*- coding: utf-8 -*-
# test_qwen_worker_v2.py
# ---------------------------------------------------------
# Qwen Worker v2 测试脚本
# - 测试任务提交流程
# - 测试 Planner + Step Executor 完整流程
# - 测试步骤状态管理
# - 测试取消机制
# ---------------------------------------------------------

import json
import time
import sys
import os

# 添加 python-worker 到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'python-worker')))

from worker_config import redis, WORKER_ID
from TaskModel_v2 import TaskModel


def test_submit_task():
    """测试提交任务到 Redis 队列"""
    
    print("\n" + "="*60)
    print("📝 测试 1: 提交任务到 Redis 队列")
    print("="*60 + "\n")
    
    # 创建测试任务
    task_id = f"test-{int(time.time() * 1000)}"
    task_type = "qwen_generate"
    payload = {
        "prompt": "写一个函数，计算两个数的和"
    }
    
    # 使用 TaskModel 创建任务
    task_submit = TaskModel.create_task_submit(
        task_id=task_id,
        task_type=task_type,
        payload=payload,
        source="test_script"
    )
    
    # 设置 meta 信息
    task_submit["meta"]["retry_count"] = 0
    task_submit["meta"]["started_at"] = int(time.time() * 1000)
    
    print("提交的任务:")
    print(TaskModel.pretty_print(task_submit))
    print()
    
    # 推送到 Redis 队列
    task_queue_key = "task_queue"
    redis.lpush(task_queue_key, json.dumps(task_submit))
    
    print(f"✅ 任务已推送到 Redis 队列：{task_queue_key}")
    print(f"   · Task ID: {task_id}")
    print(f"   · Task Type: {task_type}")
    print(f"   · Prompt: {payload['prompt']}")
    
    return task_id


def test_check_task_execution(task_id):
    """检查任务执行结果"""
    
    print("\n" + "="*60)
    print("📝 测试 2: 检查任务执行结果")
    print("="*60 + "\n")
    
    result_key = f"task_result:{task_id}"
    
    print(f"等待任务执行完成... (最多等待 60 秒)")
    print(f"监听 Redis key: {result_key}\n")
    
    # 轮询检查结果（最多等待 60 秒）
    max_wait = 60
    wait_interval = 2  # 每 2 秒检查一次
    elapsed = 0
    
    while elapsed < max_wait:
        result_json = redis.get(result_key)
        
        if result_json:
            result_data = json.loads(result_json)
            
            print("任务执行完成!")
            print("\n执行结果:")
            print(TaskModel.pretty_print(result_data))
            print()
            
            # 检查结果状态
            status = result_data.get("status")
            
            if status == "done":
                print(f"✅ 任务成功完成!")
                
                # 打印步骤信息
                steps = result_data.get("steps", [])
                if steps:
                    print(f"\n📋 执行了 {len(steps)} 个步骤:")
                    for idx, step in enumerate(steps, 1):
                        step_id = step.get("id", f"step-{idx}")
                        step_type = step.get("type", "unknown")
                        step_status = step.get("status", "unknown")
                        print(f"   {idx}. {step_id} ({step_type}): {step_status}")
                
                return True
                
            elif status == "error":
                error = result_data.get("error", {})
                print(f"❌ 任务执行失败!")
                print(f"   · 错误代码：{error.get('code', 'UNKNOWN')}")
                print(f"   · 错误信息：{error.get('message', 'Unknown error')}")
                return False
                
            elif status == "cancelled":
                print(f"🛑 任务已被取消")
                return False
        
        time.sleep(wait_interval)
        elapsed += wait_interval
        print(f"   等待中... ({elapsed}/{max_wait} 秒)")
    
    print(f"\n⚠️ 等待超时 ({max_wait} 秒)，任务可能仍在执行")
    return False


def test_cancel_task(task_id):
    """测试任务取消机制"""
    
    print("\n" + "="*60)
    print("📝 测试 3: 测试任务取消机制")
    print("="*60 + "\n")
    
    print(f"设置任务取消标记：stop:{task_id}")
    
    # 设置取消标记
    redis.set(f"stop:{task_id}", "1")
    
    print("✅ 取消标记已设置")
    print("   如果 Worker 正在执行此任务，它应该会检测到取消标记并停止执行")
    
    # 清理取消标记（实际场景中应该由 Worker 清理）
    time.sleep(2)
    redis.delete(f"stop:{task_id}")
    print("\n✅ 取消标记已清理")


def main():
    """主测试函数"""
    
    print("\n" + "="*80)
    print(" " * 20 + "QWEN WORKER V2 测试套件")
    print("="*80)
    print(f"\nWorker ID: {WORKER_ID}")
    print(f"Redis 连接：{'✅ 成功' if redis else '❌ 失败'}")
    print()
    
    try:
        # 测试 1: 提交任务
        task_id = test_submit_task()
        
        print("\n" + "-"*80)
        input(f"\n按 Enter 键启动 qwen_worker_v2.py 来执行任务...")
        print("\n💡 提示：请在另一个终端窗口运行：")
        print(f"   cd python-worker/agents/qwen")
        print(f"   python qwen_worker_v2.py\n")
        print("-"*80 + "\n")
        
        # 测试 2: 检查执行结果
        success = test_check_task_execution(task_id)
        
        # 测试 3: 取消机制（可选）
        print("\n")
        choice = input("是否测试任务取消机制？(y/n): ").strip().lower()
        if choice == 'y':
            # 先提交一个新任务
            cancel_task_id = test_submit_task()
            print("\n等待 5 秒让 Worker 开始处理任务...")
            time.sleep(5)
            test_cancel_task(cancel_task_id)
        
        print("\n" + "="*80)
        print("测试完成!")
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"\n❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
