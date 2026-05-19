# -*- coding: utf-8 -*-
# test_local_worker_fileops.py
# ---------------------------------------------------------
# 测试 Local Worker 的文件生成能力（行为对齐 Qwen Worker）
# ---------------------------------------------------------

import sys
import os
import json
import time

# 添加 python_worker 根目录到 sys.path
python_worker_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'Copilot_Alphapilot', 'python_worker'))
if python_worker_dir not in sys.path:
    sys.path.insert(0, python_worker_dir)

from worker_config import create_redis_client, get_worker_queue
from TaskModel_v2 import TaskModel

redis = create_redis_client()


def submit_test_task(prompt: str, task_type: str = "local_generate"):
    """
    提交测试任务到 Local Worker 队列
    
    Args:
        prompt: 用户提示词
        task_type: 任务类型（默认 local_generate）
    
    Returns:
        str: 任务 ID
    """
    task_id = f"test_local_{int(time.time())}"
    
    task = TaskModel.create_task_submission(
        task_id=task_id,
        task_type=task_type,
        payload={"prompt": prompt},
        meta={"test_mode": True}
    )
    
    queue_name = get_worker_queue(task_type)
    redis.lpush(queue_name, json.dumps(task))
    
    print(f"✅ 测试任务已提交:")
    print(f"   任务ID: {task_id}")
    print(f"   队列: {queue_name}")
    print(f"   提示词: {prompt[:50]}...")
    
    return task_id


def wait_for_result(task_id: str, timeout: int = 120):
    """
    等待任务执行结果
    
    Args:
        task_id: 任务 ID
        timeout: 超时时间（秒）
    
    Returns:
        dict: 任务结果
    """
    result_key = f"task_result:{task_id}"
    start_time = time.time()
    
    print(f"\n⏳ 等待任务执行结果 (timeout={timeout}s)...")
    
    while time.time() - start_time < timeout:
        result_json = redis.get(result_key)
        
        if result_json:
            result = json.loads(result_json)
            print(f"\n✅ 任务执行完成!")
            return result
        
        time.sleep(2)
        elapsed = int(time.time() - start_time)
        if elapsed % 10 == 0:
            print(f"   已等待 {elapsed}s...")
    
    raise TimeoutError(f"任务执行超时 ({timeout}s)")


def analyze_result(result: dict):
    """
    分析任务结果，检查 FileOps 生成情况
    
    Args:
        result: 任务结果字典
    """
    print("\n" + "=" * 60)
    print("📊 任务结果分析")
    print("=" * 60)
    
    # 1. 检查步骤列表
    steps = result.get("steps", [])
    print(f"\n📋 执行步骤数: {len(steps)}")
    for i, step in enumerate(steps):
        status = step.get("status", "unknown")
        step_type = step.get("type", "unknown")
        print(f"   {i+1}. {step_type}: {status}")
    
    # 2. 检查 final_file_ops
    context = result.get("context", {})
    final_file_ops = context.get("final_file_ops", [])
    
    print(f"\n📁 生成的文件数: {len(final_file_ops)}")
    
    if final_file_ops:
        for op in final_file_ops:
            path = op.get("path", "N/A")
            action = op.get("op", "N/A")
            file_type = op.get("file_type", "N/A")
            content_preview = op.get("content", "")[:50].replace("\n", " ")
            
            print(f"   - [{action}] {path} ({file_type})")
            print(f"     内容预览: {content_preview}...")
    else:
        print("   ⚠️ 未检测到 FileOps！")
        print("   可能原因:")
        print("   1. Local LLM 未遵循 # FILE: 协议格式")
        print("   2. parse_fileops_v3 解析失败")
        print("   3. write_step 或 refine_step 未正确更新 context")
    
    # 3. 检查事件流
    events = result.get("events", [])
    print(f"\n📨 事件流数量: {len(events)}")
    
    # 4. 检查结果文本
    result_text = result.get("result", "")
    if result_text:
        print(f"\n📝 结果文本长度: {len(result_text)} 字符")
        if len(result_text) > 500:
            print(f"   预览: {result_text[:200]}...")
        else:
            print(f"   内容: {result_text}")
    
    print("\n" + "=" * 60)


def main():
    """
    主测试流程
    """
    print("=" * 60)
    print("🧪 Local Worker 文件生成能力测试")
    print("=" * 60)
    
    # 测试用例 1: 简单排序函数
    print("\n\n【测试 1】简单排序函数")
    task_id_1 = submit_test_task("写一个快速排序算法")
    
    try:
        result_1 = wait_for_result(task_id_1, timeout=120)
        analyze_result(result_1)
    except TimeoutError as e:
        print(f"\n❌ 测试 1 失败: {e}")
    
    time.sleep(5)
    
    # 测试用例 2: 多文件项目
    print("\n\n【测试 2】多文件项目")
    task_id_2 = submit_test_task("创建一个计算器模块，包含 calculator.py、tests/test_calculator.py 和 README.md")
    
    try:
        result_2 = wait_for_result(task_id_2, timeout=120)
        analyze_result(result_2)
    except TimeoutError as e:
        print(f"\n❌ 测试 2 失败: {e}")
    
    print("\n\n✅ 所有测试完成！")


if __name__ == "__main__":
    main()
