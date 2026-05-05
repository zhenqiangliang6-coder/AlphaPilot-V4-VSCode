# -*- coding: utf-8 -*-
# test_all_workers.py
# ---------------------------------------------------------
# 批量测试所有 Worker (Qwen, DeepSeek, Doubao)
# - 同时提交任务到三个 Worker
# - 对比执行结果和性能
# ---------------------------------------------------------

import json
import time
import sys
import os

# 添加 python-worker 到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'python-worker')))

from worker_config import redis, WORKER_ID, get_worker_queue  # ⭐ 新增：导入队列路由函数
from TaskModel_v2 import TaskModel


# ============================
# 测试配置
# ============================

TEST_PROMPT = "写一个函数，计算斐波那契数列的第 n 项"

WORKERS = {
    "qwen": {
        "task_type": "qwen_generate",
        "worker_module": "agents.qwen.qwen_worker_v2"
    },
    "deepseek": {
        "task_type": "deepseek_generate",
        "worker_module": "agents.deepeek.deepseek_worker_v2"
    },
    "doubao": {
        "task_type": "doubao_generate",
        "worker_module": "agents.Volcengine.doubao_worker_v2"
    }
}


def submit_all_tasks():
    """向所有 Worker 提交任务"""
    
    print("\n" + "="*80)
    print("批量提交任务到所有 Worker")
    print("="*80 + "\n")
    
    task_ids = {}
    
    for model_key, config in WORKERS.items():
        task_id = f"test-{model_key}-{int(time.time() * 1000)}"
        task_type = config["task_type"]
        
        # 创建任务
        task_submit = TaskModel.create_task_submit(
            task_id=task_id,
            task_type=task_type,
            payload={"prompt": TEST_PROMPT},
            source="batch_test"
        )
        
        task_submit["meta"]["retry_count"] = 0
        task_submit["meta"]["started_at"] = int(time.time() * 1000)
        
        # ⭐ 根据任务类型路由到专属队列（符合多智能体架构）
        queue_name = get_worker_queue(task_type)
        redis.lpush(queue_name, json.dumps(task_submit))
        task_ids[model_key] = task_id
        
        print(f"✅ {model_key.upper()} 任务已提交")
        print(f"   · Task ID: {task_id}")
        print(f"   · Queue: {queue_name}")
        print(f"   · Prompt: {TEST_PROMPT}")
        print()
    
    return task_ids


def check_all_results(task_ids):
    """检查所有任务的执行结果"""
    
    print("\n" + "="*80)
    print("等待所有任务执行完成...")
    print("="*80 + "\n")
    
    results = {}
    max_wait = 120
    wait_interval = 3
    elapsed = 0
    
    while elapsed < max_wait:
        all_done = True
        
        for model_key, task_id in task_ids.items():
            if model_key in results:
                continue
            
            result_key = f"task_result:{task_id}"
            result_json = redis.get(result_key)
            
            if result_json:
                result_data = json.loads(result_json)
                results[model_key] = result_data
                
                status = result_data.get("status")
                duration = result_data.get("meta", {}).get("duration_ms", 0)
                
                if status == "done":
                    print(f"✅ {model_key.upper()} 成功完成! (耗时：{duration/1000:.2f}s)")
                elif status == "error":
                    error = result_data.get("error", {})
                    print(f"❌ {model_key.upper()} 失败：{error.get('message', 'Unknown')[:50]}")
                elif status == "cancelled":
                    print(f"🛑 {model_key.upper()} 已被取消")
            else:
                all_done = False
        
        if all_done:
            break
        
        time.sleep(wait_interval)
        elapsed += wait_interval
        print(f"等待中... ({elapsed}/{max_wait} 秒) - 已完成：{len(results)}/{len(task_ids)}")
    
    return results


def print_comparison(results):
    """打印对比结果"""
    
    print("\n" + "="*80)
    print("测试结果对比")
    print("="*80 + "\n")
    
    # 成功统计
    success_count = sum(1 for r in results.values() if r.get("status") == "done")
    error_count = sum(1 for r in results.values() if r.get("status") == "error")
    
    print(f"📊 总体统计:")
    print(f"   · 总任务数：{len(results)}")
    print(f"   · 成功：{success_count}")
    print(f"   · 失败：{error_count}")
    print()
    
    # 详细结果
    print("📋 详细结果:\n")
    
    for model_key, result in results.items():
        print(f"{model_key.upper()}:")
        print(f"   状态：{result.get('status', 'unknown')}")
        
        if result.get("status") == "done":
            duration = result.get("meta", {}).get("duration_ms", 0)
            print(f"   耗时：{duration/1000:.2f} 秒")
            
            steps = result.get("steps", [])
            if steps:
                print(f"   步骤数：{len(steps)}")
                for step in steps:
                    step_type = step.get("type", "unknown")
                    step_status = step.get("status", "unknown")
                    print(f"      - {step_type}: {step_status}")
        
        elif result.get("status") == "error":
            error = result.get("error", {})
            print(f"   错误：{error.get('message', 'Unknown')[:100]}")
        
        print()


def main():
    """主测试函数"""
    
    print("\n" + "="*80)
    print(" " * 20 + "多模型 Worker 批量测试")
    print("="*80)
    print(f"\nRedis 连接：{'✅ 成功' if redis else '❌ 失败'}")
    print(f"测试 Prompt: {TEST_PROMPT}")
    
    try:
        # 提交所有任务
        task_ids = submit_all_tasks()
        
        print("\n" + "-"*80)
        print("\n💡 提示：请确保以下 Worker 正在运行:")
        for model_key, config in WORKERS.items():
            print(f"   · {model_key.upper()}: python -m {config['worker_module']}")
        print()
        print("-"*80 + "\n")
        
        input("按 Enter 键开始检查所有任务的执行结果...")
        
        # 检查结果
        results = check_all_results(task_ids)
        
        # 打印对比
        print_comparison(results)
        
        print("\n" + "="*80)
        print("批量测试完成!")
        print("="*80 + "\n")
        
        # 返回测试结果
        success_count = sum(1 for r in results.values() if r.get("status") == "done")
        sys.exit(0 if success_count > 0 else 1)
        
    except Exception as e:
        print(f"\n❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
