# -*- coding: utf-8 -*-
# doubao_worker_v2.py
# ---------------------------------------------------------
# Doubao Worker v2（标准化智能体执行引擎）
# - 从 Redis 取任务
# - 调用 Planner（任务拆解）
# - 调用 Step Executor（多步骤执行）
# - 写入 TaskModel v2 结果
# - 写入 DLQ（死信队列）
# - ⭐ 支持多模态输入（图片 + 文本）
# - ⭐ 步骤状态管理（pending → running → success / error）
# ---------------------------------------------------------

import json
import time
import traceback
from dotenv import load_dotenv

from ...worker_config import (
    redis,
    WORKER_ID,
    create_empty_context,
    check_stop_flag,
    clear_stop_flag,
    get_worker_queue,  # ⭐ 新增：队列路由函数
)

# ⭐ 修复：导入 Doubao 专用的 Planner，不再依赖全局 planner.py（Qwen）
from .doubao_planner import llm_decompose_task
from .step_executor import execute_step
from ...TaskModel_v2 import TaskModel

# Doubao 专用配置
DOUBAO_API_KEY = None
MODEL_NAME = "doubao-seed-2-0-lite-260215"

try:
    from dotenv import load_dotenv
    load_dotenv()
    import os
    DOUBAO_API_KEY = os.getenv("VOLC_API_KEY")
    MODEL_NAME = os.getenv("DOUBAO_MODEL", "doubao-seed-2-0-lite-260215")
except Exception as e:
    print(f"⚠️ 加载环境变量失败：{e}")


def execute_task(task_type: str, payload: dict, task_id: str, steps: list, events: list, context: dict):
    """
    Worker 的统一入口（v2）：
    - doubao_generate → Planner + 多步骤执行
    - doubao_multimodal → 多模态任务处理
    - 其它任务类型可逐步迁移
    """
    if task_type == "doubao_generate":
        prompt = payload.get("prompt", "")
        image_url = payload.get("image_url")  # 可选的图片 URL
        
        if not prompt:
            raise ValueError("prompt 不能为空")

        # ---------------------------------------------------------
        # 1) 调用 Planner：让 Doubao 拆解任务
        # ---------------------------------------------------------
        plan_steps = llm_decompose_task(prompt)
        steps.extend(plan_steps)

        # ---------------------------------------------------------
        # 2) 依次执行每个步骤（新增：步骤状态管理 + 取消检查）
        # ---------------------------------------------------------
        for step in steps:
            try:
                # ⭐ 检查是否被取消（在每个步骤执行前）
                if check_stop_flag(task_id):
                    step["status"] = "failed"  # ✅ 修复：使用前端协议的状态值
                    step["output"] = {"text": "任务已被用户取消"}
                    raise Exception("任务已被用户取消")

                # ⭐ 状态：pending → running
                step["status"] = "running"

                # 执行步骤（传入 Doubao 专用的 call_doubao，带图片参数）
                api_func_with_image = lambda p: call_doubao_wrapper(p, image_url)
                execute_step(task_id, step, events, context, api_func=api_func_with_image)

                # ⭐ 状态：running → completed (修复：success → completed)
                step["status"] = "completed"

            except Exception as step_error:
                # ⭐ 如果是取消异常，保持 failed 状态
                if "取消" in str(step_error) or "cancel" in str(step_error).lower():
                    step["status"] = "failed"  # ✅ 修复：使用前端协议的状态值
                    step["output"] = {"text": "任务已被用户取消"}
                else:
                    # ⭐ 状态：running → failed (修复：error → failed)
                    step["status"] = "failed"  # ✅ 修复：使用前端协议的状态值
                    step["output"] = {"text": f"步骤执行失败：{step_error}"}
                raise step_error

        # ---------------------------------------------------------
        # 3) 最终结果：取最后一个步骤的 output
        # ---------------------------------------------------------
        last_output = steps[-1].get("output", {})
        return last_output.get("text", "")

    elif task_type == "doubao_multimodal":
        # 专门的多模态任务处理
        prompt = payload.get("prompt", "")
        image_url = payload.get("image_url")
        
        if not prompt:
            raise ValueError("prompt 不能为空")
        if not image_url:
            raise ValueError("多模态任务需要提供 image_url")
        
        # 直接使用 API 调用（不走 planner）
        result = call_doubao_wrapper(prompt, image_url)
        return result

    else:
        raise ValueError(f"未知任务类型：{task_type}")


def call_doubao_wrapper(prompt: str, image_url: str = None) -> str:
    """
    Doubao API 调用包装器
    """
    from .doubao_api import call_doubao
    return call_doubao(prompt, image_url)


# =========================
# 主循环：从 Redis 取任务 → 执行 → 写回结果（v2）
# =========================

def main_loop():
    dlq_key = "dlq"
    
    # ⭐ 获取 Doubao Worker 专属队列（符合多智能体架构）
    queue_name = get_worker_queue("doubao_generate")
    print(f"📡 监听队列: {queue_name}")

    while True:
        try:
            result_key = None  # ⭐ 必须提前定义，否则 except 会报错

            # ---------------------------------------------------------
            # 从专属队列取任务
            # ---------------------------------------------------------
            task_json = redis.rpop(queue_name)
            if not task_json:
                time.sleep(2)
                continue

            task = json.loads(task_json)

            print("\n" + "="*60)
            print("收到任务:")
            print(TaskModel.pretty_print(task))
            print("="*60 + "\n")

            # v2 正确字段
            task_id = task["task_id"]
            task_type = task["type"]
            payload = task["payload"]
            
            # ⭐ 二次验证：确保任务类型匹配（尊重 Worker 真相地位）
            if not task_type.startswith("doubao_"):
                # 如果错误地收到了非 Doubao 任务，放回原队列并记录警告
                redis.lpush(queue_name, task_json)
                print(f"⚠️ 收到不匹配的任务类型: {task_type}，已放回队列")
                time.sleep(1)
                continue

            # ⭐ 初始化 meta 字段（如果不存在）
            if "meta" not in task:
                task["meta"] = {
                    "retry_count": 0,
                    "started_at": int(time.time() * 1000),
                    "worker_id": WORKER_ID  # ✅ 使用从 worker_config 导入的常量
                }
            
            retry_count = task["meta"].get("retry_count", 0)
            started_at = task["meta"].get("started_at", int(time.time() * 1000))

            # 初始化 v2 容器
            steps = []
            events = []
            context = create_empty_context()

            # ---------------------------------------------------------
            # 执行任务（Planner + 多步骤）
            # ---------------------------------------------------------
            result = execute_task(task_type, payload, task_id, steps, events, context)

            # ---------------------------------------------------------
            # 写回成功结果
            # ---------------------------------------------------------
            result_key = f"task_result:{task_id}"
            result_data = TaskModel.create_task_result_success(
                task_id=task_id,
                task_type=task_type,
                result=result,
                worker_id=WORKER_ID,
                started_at=started_at,
                steps=steps,
                events=events,
                context=context
            )

            redis.set(result_key, json.dumps(result_data))

            print("\n" + "="*60)
            print("任务完成，结果已写入 Redis:")
            print(TaskModel.pretty_print(result_data))
            print("="*60 + "\n")

            # ⭐ 清理取消标记
            clear_stop_flag(task_id)

        except Exception as e:
            # ⭐ 判断是否是取消操作
            is_cancelled = "取消" in str(e) or "cancel" in str(e).lower()
            
            # ---------------------------------------------------------
            # 构造错误结果（区分取消和真实错误）
            # ---------------------------------------------------------
            if is_cancelled:
                # 任务被取消
                error_result = TaskModel.create_task_result_error(
                    task_id=task_id,
                    task_type=task_type,
                    error_message="任务已被用户取消",
                    worker_id=WORKER_ID,
                    error_code="TASK_CANCELLED",
                    error_stack=None,
                    started_at=started_at,
                    retry_count=retry_count,
                    steps=steps,
                    events=events,
                    context=context
                )
                
                print("\n" + "="*60)
                print("🛑 任务已被用户取消")
                print("="*60 + "\n")
            else:
                # 真实错误
                error_result = TaskModel.create_task_result_error(
                    task_id=task_id,
                    task_type=task_type,
                    error_message=str(e),
                    worker_id=WORKER_ID,
                    error_code="MODEL_CALL_ERROR",
                    error_stack=traceback.format_exc(),
                    started_at=started_at,
                    retry_count=retry_count,
                    steps=steps,
                    events=events,
                    context=context
                )
                
                print("\n" + "="*60)
                print("任务失败，错误结果已写入 Redis:")
                print(TaskModel.pretty_print(error_result))
                print("="*60 + "\n")

            # 只有 result_key 已经生成时才写入
            if result_key:
                redis.set(result_key, json.dumps(error_result))

            # ⭐ 清理取消标记
            clear_stop_flag(task_id)

            # ---------------------------------------------------------
            # 写入 DLQ（死信队列）- 只对真实错误
            # ---------------------------------------------------------
            if not is_cancelled:
                dlq_item = TaskModel.create_dlq_item(
                    original_task=task,
                    failure_record={
                        "error_message": str(e),
                        "error_stack": traceback.format_exc(),
                        "retry_count": retry_count,
                        "retryable": True
                    },
                    retry_count=retry_count,
                    first_failed_at=int(time.time() * 1000)
                )

                redis.lpush(dlq_key, json.dumps(dlq_item))

                print("\n" + "="*60)
                print("任务已写入死信队列:")
                print(TaskModel.pretty_print(dlq_item))
                print("="*60 + "\n")


if __name__ == "__main__":
    print("\n🚀 Doubao Worker v2 已启动")
    print(f"   · Worker ID: {WORKER_ID}")
    print(f"   · Model: {MODEL_NAME}")
    print(f"   · Node API: 已连接")
    print(f"   · 正在监听任务队列...\n")
    main_loop()
