# -*- coding: utf-8 -*-
# agents/tencent_maas/maas_worker.py
# ---------------------------------------------------------
# 腾讯 MaaS Worker
# - 处理 maas_generate 任务（队列 task_queue:maas）
# - 复用 Local LLM Worker 的执行链 / 人格 / step_executor
#   （腾讯 MaaS 与 LM Studio 同为 OpenAI 兼容端点）
# ---------------------------------------------------------

import sys
import os
import time
import json
import traceback
import requests

# 确保 python_worker 根目录在 sys.path 中
current_dir = os.path.dirname(os.path.abspath(__file__))
python_worker_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))
if python_worker_dir not in sys.path:
    sys.path.insert(0, python_worker_dir)

from worker_config import (
    NODE_API_URL,
    WORKER_ID,
    create_redis_client,
    get_worker_queue,
    check_stop_flag,
    clear_stop_flag,
    create_empty_context,
)
from TaskModel_v2 import TaskModel
from intent_router import IntentRouter
from agents.local_llm.personas import get_persona_config
from agents.local_llm.step_executor import execute_step
from agents.local_llm.local_worker_v3 import BASE_CHAIN, INTENT_CHAINS, create_steps_from_chain
from agents.tencent_maas.maas_api import call_maas

redis = create_redis_client()

TASK_TYPE = "maas_generate"
TASK_PREFIX = "maas_"
DLQ_NAME = "dlq"


def call_maas_wrapper(prompt: str, task_id: str = None) -> str:
    """腾讯 MaaS 调用包装器（启用流式输出）"""
    return call_maas(prompt, stream=True, task_id=task_id)


def execute_task(task_type: str, payload: dict, task_id: str, steps: list, events: list, context: dict):
    """
    腾讯 MaaS Worker 统一入口：
    - 处理 maas_generate 任务
    - Intent Router + Persona + Execution Chain + 多步骤执行
    """
    if task_type != TASK_TYPE:
        raise ValueError(f"不支持的任务类型：{task_type}")

    prompt = payload.get("prompt", "")
    if not prompt:
        raise ValueError("prompt 不能为空")

    intent, persona_type, _ = IntentRouter.detect_intent(prompt)
    persona_config = get_persona_config(persona_type)
    execution_chain = INTENT_CHAINS.get(intent, BASE_CHAIN)

    context["meta"] = {
        "intent": intent,
        "persona": persona_type,
        "persona_config": persona_config,
        "execution_chain": execution_chain,
    }
    context["user_query"] = prompt

    print("\n🧠 腾讯 MaaS Worker 决策：")
    print(f"  意图: {intent}")
    print(f"  人格: {persona_config['name']} ({persona_config['icon']})")
    print(f"  执行链: {' → '.join(execution_chain)}")

    if not steps:
        steps.extend(create_steps_from_chain(execution_chain, prompt, persona_type, intent))
        print(f"\n📋 动态生成 {len(steps)} 个步骤 (意图: {intent})")

    for step in steps:
        try:
            if check_stop_flag(task_id):
                step["status"] = "failed"
                step["output"] = {"text": "任务已被用户取消"}
                raise Exception("任务已被用户取消")

            step["status"] = "running"
            context["_custom_api_func"] = lambda p: call_maas_wrapper(p, task_id)

            execute_step(task_id, step, events, context)

            if "_custom_api_func" in context:
                del context["_custom_api_func"]

            step["status"] = "completed"

        except Exception as step_error:
            msg = str(step_error)
            step["status"] = "failed"
            if "取消" in msg or "cancel" in msg.lower():
                step["output"] = {"text": "任务已被用户取消"}
            else:
                step["output"] = {"text": f"步骤执行失败：{step_error}"}
            raise step_error

    last_output = steps[-1].get("output", {})
    return last_output.get("text", "")


def _notify_node_api(task_id: str, result_data: dict, label: str = "任务"):
    try:
        notify_url = f"{NODE_API_URL}/task/notify/{task_id}"
        print(f"\n📡 正在通知 Node.js（{label}）: {notify_url}")
        response = requests.post(
            notify_url,
            json=result_data,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if response.status_code == 200:
            print("✅ Node.js 已成功接收通知，将推送给前端")
        else:
            print(f"⚠️ Node.js 返回错误状态码: {response.status_code}")
    except Exception as notify_error:
        print(f"⚠️ 通知 Node.js 失败: {notify_error}")


def main_loop():
    queue_name = get_worker_queue(TASK_TYPE)
    print(f"📡 腾讯 MaaS Worker 监听队列: {queue_name}")

    while True:
        task = None
        task_id = None
        task_type = None
        started_at = None
        retry_count = 0
        steps = []
        events = []
        context = create_empty_context()

        try:
            task_json = redis.rpop(queue_name)
            if not task_json:
                time.sleep(2)
                continue

            task = json.loads(task_json)

            print("\n" + "=" * 60)
            print("收到任务:")
            print(TaskModel.pretty_print(task))
            print("=" * 60 + "\n")

            task_id = task["task_id"]
            task_type = task.get("task_type") or task.get("type")

            if task_type and not task_type.startswith(TASK_PREFIX):
                redis.lpush(queue_name, task_json)
                print(f"⚠️ 收到不匹配的任务类型: {task_type}，已放回队列")
                time.sleep(1)
                continue

            meta = task.get("meta", {})
            retry_count = meta.get("retry_count", 0)
            started_at = meta.get("started_at", int(time.time() * 1000))

            context["final_file_ops"] = []

            result = execute_task(task_type, task["payload"], task_id, steps, events, context)

            result_key = f"task_result:{task_id}"
            result_data = TaskModel.create_task_result_success(
                task_id=task_id,
                task_type=task_type,
                result=result,
                worker_id=WORKER_ID,
                started_at=started_at,
                steps=steps,
                events=events,
                context=context,
            )
            redis.set(result_key, json.dumps(result_data))

            print("\n" + "=" * 60)
            print("任务完成，结果已写入 Redis:")
            print(TaskModel.pretty_print(result_data))
            print("=" * 60 + "\n")

            _notify_node_api(task_id, result_data)
            clear_stop_flag(task_id)

        except Exception as e:
            is_cancelled = "取消" in str(e) or "cancel" in str(e).lower()

            error_result = TaskModel.create_task_result_error(
                task_id=task_id,
                task_type=task_type,
                error_message="任务已被用户取消" if is_cancelled else str(e),
                worker_id=WORKER_ID,
                error_code="TASK_CANCELLED" if is_cancelled else "MODEL_CALL_ERROR",
                error_stack=None if is_cancelled else traceback.format_exc(),
                started_at=started_at,
                retry_count=retry_count,
                steps=steps,
                events=events,
                context=context,
            )

            print("\n" + "=" * 60)
            print("🛑 任务已被用户取消" if is_cancelled else "任务失败，错误结果已写入 Redis:")
            print(TaskModel.pretty_print(error_result))
            print("=" * 60 + "\n")

            if task_id:
                redis.set(f"task_result:{task_id}", json.dumps(error_result))
                _notify_node_api(task_id, error_result, label="错误任务")
                clear_stop_flag(task_id)

            if task and not is_cancelled:
                dlq_item = TaskModel.create_dlq_item(
                    original_task=task,
                    failure_record={
                        "error_message": str(e),
                        "error_stack": traceback.format_exc(),
                        "retry_count": retry_count,
                        "retryable": True,
                    },
                    retry_count=retry_count,
                    first_failed_at=int(time.time() * 1000),
                )
                redis.lpush(DLQ_NAME, json.dumps(dlq_item))

                print("\n" + "=" * 60)
                print("任务已写入死信队列:")
                print(TaskModel.pretty_print(dlq_item))
                print("=" * 60 + "\n")


if __name__ == "__main__":
    print("\n🚀 腾讯 MaaS Worker 已启动")
    print(f"   · Worker ID: {WORKER_ID}")
    print(f"   · 模型: {os.getenv('TENCENT_MAAS_MODEL', 'hy4-preview')}")
    print(f"   · 正在监听任务队列...\n")
    main_loop()
