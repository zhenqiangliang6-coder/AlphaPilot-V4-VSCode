# -*- coding: utf-8 -*-
"""
测试 Worker 导入
验证 Qwen Worker 和 Local LLM Worker 是否能正常导入
"""

import sys
import os

# 添加 python_worker 到 sys.path
python_worker_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'python_worker')
if python_worker_dir not in sys.path:
    sys.path.insert(0, python_worker_dir)

print("=" * 60)
print("测试 Worker 导入")
print("=" * 60)

# 测试 1: 导入 worker_config
print("\n[1/4] 测试导入 worker_config...")
try:
    from python_worker.worker_config import (
        redis,
        WORKER_ID,
        create_empty_context,
        check_stop_flag,
        clear_stop_flag,
        get_worker_queue,
        NODE_API_URL,
    )
    print("✅ worker_config 导入成功")
except Exception as e:
    print(f"❌ worker_config 导入失败: {e}")
    import traceback
    traceback.print_exc()

# 测试 2: 导入 TaskModel_v2
print("\n[2/4] 测试导入 TaskModel_v2...")
try:
    from python_worker.TaskModel_v2 import TaskModel
    print("✅ TaskModel_v2 导入成功")
except Exception as e:
    print(f"❌ TaskModel_v2 导入失败: {e}")
    import traceback
    traceback.print_exc()

# 测试 3: 导入 Qwen Worker
print("\n[3/4] 测试导入 Qwen Worker...")
try:
    from python_worker.agents.qwen.qwen_worker_v2 import main_loop as qwen_main
    print("✅ Qwen Worker 导入成功")
except Exception as e:
    print(f"❌ Qwen Worker 导入失败: {e}")
    import traceback
    traceback.print_exc()

# 测试 4: 导入 Local LLM Worker
print("\n[4/4] 测试导入 Local LLM Worker...")
try:
    from python_worker.agents.local_llm.local_worker_v3 import main_loop as local_main
    print("✅ Local LLM Worker 导入成功")
except Exception as e:
    print(f"❌ Local LLM Worker 导入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
