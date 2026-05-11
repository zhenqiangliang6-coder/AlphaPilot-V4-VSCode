# -*- coding: utf-8 -*-
# test_worker_v3_upgrade.py
# ---------------------------------------------------------
# AlphaPilot OS v3.1 - Worker 升级验证脚本
# 测试 DeepSeek Worker v3.0 和 Doubao Worker v3.0
# ---------------------------------------------------------

import json
import time
import sys
import os

# 添加 python_worker 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python_worker'))

from worker_config import redis, get_worker_queue

def test_deepseek_worker():
    """测试 DeepSeek Worker v3.0"""
    print("\n" + "="*60)
    print("🧪 测试 DeepSeek Worker v3.0")
    print("="*60)
    
    task_id = f"test-deepseek-{int(time.time())}"
    task = {
        "task_id": task_id,
        "type": "deepseek_generate",
        "payload": {
            "prompt": "创建一个 Python 函数计算斐波那契数列，并添加完整的 docstring"
        },
        "meta": {
            "retry_count": 0,
            "started_at": int(time.time() * 1000)
        }
    }
    
    queue_name = get_worker_queue("deepseek_generate")
    print(f"\n📤 提交任务到队列: {queue_name}")
    print(f"   Task ID: {task_id}")
    print(f"   Prompt: {task['payload']['prompt']}")
    
    redis.lpush(queue_name, json.dumps(task))
    print(f"\n✅ 任务已提交！")
    print(f"\n💡 提示: 启动 DeepSeek Worker v3.0 查看执行结果:")
    print(f"   cd python_worker/agents/deepeek")
    print(f"   python deepseek_worker_v3.py")
    
    return task_id


def test_doubao_worker():
    """测试 Doubao Worker v3.0"""
    print("\n" + "="*60)
    print("🧪 测试 Doubao Worker v3.0")
    print("="*60)
    
    task_id = f"test-doubao-{int(time.time())}"
    task = {
        "task_id": task_id,
        "type": "doubao_generate",
        "payload": {
            "prompt": "解释以下代码的功能：\n\ndef fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)"
        },
        "meta": {
            "retry_count": 0,
            "started_at": int(time.time() * 1000)
        }
    }
    
    queue_name = get_worker_queue("doubao_generate")
    print(f"\n📤 提交任务到队列: {queue_name}")
    print(f"   Task ID: {task_id}")
    print(f"   Prompt: {task['payload']['prompt'][:50]}...")
    
    redis.lpush(queue_name, json.dumps(task))
    print(f"\n✅ 任务已提交！")
    print(f"\n💡 提示: 启动 Doubao Worker v3.0 查看执行结果:")
    print(f"   cd python_worker/agents/Volcengine")
    print(f"   python doubao_worker_v3.py")
    
    return task_id


def test_doubao_multimodal():
    """测试 Doubao Worker v3.0 多模态任务（向后兼容）"""
    print("\n" + "="*60)
    print("🧪 测试 Doubao Worker v3.0 - 多模态任务")
    print("="*60)
    
    task_id = f"test-doubao-multimodal-{int(time.time())}"
    task = {
        "task_id": task_id,
        "type": "doubao_multimodal",
        "payload": {
            "prompt": "描述这张图片的内容",
            "image_url": "https://example.com/test-image.jpg"  # 替换为真实图片 URL
        },
        "meta": {
            "retry_count": 0,
            "started_at": int(time.time() * 1000)
        }
    }
    
    queue_name = get_worker_queue("doubao_generate")
    print(f"\n📤 提交多模态任务到队列: {queue_name}")
    print(f"   Task ID: {task_id}")
    print(f"   Image URL: {task['payload']['image_url']}")
    
    redis.lpush(queue_name, json.dumps(task))
    print(f"\n✅ 多模态任务已提交！")
    print(f"\n⚠️ 注意: 请确保 image_url 是有效的图片链接")
    
    return task_id


def check_redis_connection():
    """检查 Redis 连接"""
    print("\n" + "="*60)
    print("🔍 检查 Redis 连接")
    print("="*60)
    
    try:
        result = redis.ping()
        print(f"\n✅ Redis 连接正常: {result}")
        return True
    except Exception as e:
        print(f"\n❌ Redis 连接失败: {e}")
        return False


def main():
    """主函数"""
    print("\n" + "="*60)
    print("🚀 AlphaPilot OS v3.1 - Worker 升级验证")
    print("="*60)
    
    # 1. 检查 Redis 连接
    if not check_redis_connection():
        print("\n❌ 请先确保 Redis 服务正常运行")
        return
    
    # 2. 选择测试类型
    print("\n请选择测试类型:")
    print("  1. 测试 DeepSeek Worker v3.0")
    print("  2. 测试 Doubao Worker v3.0")
    print("  3. 测试 Doubao Worker v3.0 - 多模态任务")
    print("  4. 全部测试")
    print("  0. 退出")
    
    choice = input("\n请输入选项 (0-4): ").strip()
    
    if choice == "1":
        test_deepseek_worker()
    elif choice == "2":
        test_doubao_worker()
    elif choice == "3":
        test_doubao_multimodal()
    elif choice == "4":
        test_deepseek_worker()
        time.sleep(1)
        test_doubao_worker()
        time.sleep(1)
        test_doubao_multimodal()
    elif choice == "0":
        print("\n👋 退出测试")
        return
    else:
        print("\n❌ 无效选项")
        return
    
    print("\n" + "="*60)
    print("✅ 测试任务已提交！")
    print("="*60)
    print("\n📋 下一步操作:")
    print("  1. 启动对应的 Worker v3.0")
    print("  2. 观察 Worker 输出日志")
    print("  3. 检查 Redis 中的任务结果")
    print("  4. 验证 Node API 是否收到通知")
    print("\n💡 提示: 按 Ctrl+C 停止 Worker")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 测试已中断")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
