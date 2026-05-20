# -*- coding: utf-8 -*-
# qwen_worker_v3.py
# ---------------------------------------------------------
# Qwen Worker v3.0 — 世界级执行链架构版
# - Intent Router：意图识别
# - Persona Engine：执行链人格（engineer/creator/conversational）
# - Execution Chain：analyze → plan → write → refine → test → fix → doc → docstring → profile
# - FileOps：多文件协议 v3.0（FILE/TEST/DOC/META/DEPENDS）
# - 与现有 step_executor 完全兼容（最小侵入升级）
# ---------------------------------------------------------

import json
import time
import traceback
import requests

from ...worker_config import (
    redis,
    WORKER_ID,
    create_empty_context,
    check_stop_flag,
    clear_stop_flag,
    get_worker_queue,
    NODE_API_URL,
)

from ...planner import llm_decompose_task
from ...intent_router import IntentRouter
from .step_executor import execute_step
from .personas import get_persona_config
from ...TaskModel_v2 import TaskModel


# =========================================================
# v3.0：执行链定义（按意图动态裁剪）
# =========================================================

BASE_CHAIN = ["analyze", "plan", "write", "refine", "test", "fix", "doc", "docstring", "profile"]

INTENT_CHAINS = {
    "write_code": ["analyze", "plan", "write", "refine", "test", "fix", "doc", "docstring"],
    "generate_doc": ["analyze", "plan", "write", "doc", "docstring"],
    "explain_code": ["analyze", "plan", "doc"],
    "creative_writing": ["analyze", "plan", "write", "refine"],
    "chat": ["analyze", "write"],
}


def build_execution_chain(intent: str) -> list:
    """
    根据意图选择执行链；未知意图使用默认 BASE_CHAIN。
    """
    return INTENT_CHAINS.get(intent, BASE_CHAIN)


# =========================================================
# v3.0：根据执行链构建步骤（与现有 step_executor 协议对齐）
# =========================================================

def create_steps_from_chain(execution_chain: list, prompt: str, persona: str, intent: str = None) -> list:
    """
    v3.0：根据执行链动态生成步骤定义。
    - 不在这里做复杂逻辑，复杂逻辑交给各 step_xxx.py
    """
    steps = []
    step_templates = {
        "analyze": {
            "type": "analyze",
            "input": {"prompt": prompt}
        },
        "plan": {
            "type": "plan",
            "input": {"prompt": "根据分析结果制定执行计划"}
        },
        "write": {
            "type": "write",
            "input": {"prompt": f"根据 {persona} 人格生成代码/内容"}
        },
        "refine": {
            "type": "refine",
            "input": {"prompt": "根据执行结果优化代码（多文件协议 v3.0）"}
        },
        "test": {
            "type": "test",
            "input": {"prompt": "为代码生成并执行 pytest 风格测试"}
        },
        "fix": {
            "type": "fix",
            "input": {"prompt": "根据错误信息修复代码"}
        },
        "doc": {
            "type": "doc",
            "input": {"prompt": "为代码生成 Markdown 文档"}
        },
        "docstring": {
            "type": "docstring",
            "input": {"prompt": "为代码添加完整 docstring（多文件）"}
        },
        "profile": {
            "type": "profile",
            "input": {"prompt": "分析代码性能并给出优化建议"}
        },
    }

    for i, step_type in enumerate(execution_chain):
        tmpl = step_templates.get(step_type)
        if not tmpl:
            continue
        step = tmpl.copy()
        step["id"] = f"step-{i+1}"
        step["status"] = "pending"
        steps.append(step)

    return steps


# =========================================================
# v3.0：统一任务执行入口
# =========================================================

def execute_task(task_type: str, payload: dict, task_id: str, steps: list, events: list, context: dict):
    """
    Qwen Worker v3.0 统一入口：
    - 只处理 qwen_generate 任务
    - Intent Router + Persona + Execution Chain
    - 多步骤执行 + FileOps 全链路
    """
    if task_type != "qwen_generate":
        raise ValueError(f"不支持的任务类型：{task_type}")

    prompt = payload.get("prompt", "")
    if not prompt:
        raise ValueError("prompt 不能为空")

    # 1) 意图识别 + 人格选择
    intent, persona_type, _ = IntentRouter.detect_intent(prompt)
    persona_config = get_persona_config(persona_type)

    # 2) 构建执行链
    execution_chain = build_execution_chain(intent)

    # 写入 meta
    context["meta"] = {
        "intent": intent,
        "persona": persona_type,
        "persona_config": persona_config,
        "execution_chain": execution_chain,
    }

    print("\n🧠 Qwen Worker v3.0 决策：")
    print(f"  意图: {intent}")
    print(f"  人格: {persona_config['name']} ({persona_config['icon']})")
    print(f"  执行链: {' → '.join(execution_chain)}")

    # 3) 如果外部未传入 steps，则根据执行链动态生成
    if not steps:
        steps.extend(create_steps_from_chain(execution_chain, prompt, persona_type, intent))
        print(f"\n📋 动态生成 {len(steps)} 个步骤 (意图: {intent})")

    # 4) Planner 兜底（可选）
    if not steps:
        plan_steps = llm_decompose_task(prompt)
        steps.extend(plan_steps)

    # 5) 逐步执行（带取消检查 + 状态管理）
    for step in steps:
        try:
            if check_stop_flag(task_id):
                step["status"] = "failed"
                step["output"] = {"text": "任务已被用户取消"}
                raise Exception("任务已被用户取消")

            step["status"] = "running"

            # 交给通用 step_executor.execute_step
            execute_step(task_id, step, events, context)

            step["status"] = "completed"

        except Exception as step_error:
            msg = str(step_error)
            if "取消" in msg or "cancel" in msg.lower():
                step["status"] = "failed"
                step["output"] = {"text": "任务已被用户取消"}
            else:
                step["status"] = "failed"
                step["output"] = {"text": f"步骤执行失败：{step_error}"}
            raise step_error

    # 6) 返回最后一步的输出
    last_output = steps[-1].get("output", {})
    return last_output.get("text", "")


# =========================================================
# 主循环：从 Redis 取任务 → 执行 → 写回结果
# =========================================================

def main_loop():
    dlq_key = "dlq"
    queue_name = get_worker_queue("qwen_generate")
    print(f"📡 Qwen Worker v3.0 监听队列: {queue_name}")

    while True:
        try:
            result_key = None

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
            payload = task["payload"]

            # 只处理 qwen_generate
            if task_type and not task_type.startswith("qwen_"):
                redis.lpush(queue_name, task_json)
                print(f"⚠️ 收到不匹配的任务类型: {task_type}，已放回队列")
                time.sleep(1)
                continue

            meta = task.get("meta", {})
            retry_count = meta.get("retry_count", 0)
            started_at = meta.get("started_at", int(time.time() * 1000))

            steps = []
            events = []
            context = create_empty_context()
            
            # ⭐ 初始化 final_file_ops（唯一真相源）
            context["final_file_ops"] = []
            
            # ⭐ v3.5 新增：加载并注入上下文记忆
            task_context = task.get("context", None)
            if task_context:
                print("\n🧠 [Memory] 检测到上下文记忆，正在注入...")
                context["memory"] = task_context
                
                # 打印上下文摘要
                project_ctx = task_context.get("project_context", {})
                memory_ctx = task_context.get("memory_context", {})
                
                print(f"   - 项目: {project_ctx.get('name', 'N/A')}")
                print(f"   - 技术栈: {json.dumps(project_ctx.get('tech_stack', {}), ensure_ascii=False)}")
                print(f"   - 用户偏好: {len(memory_ctx.get('user_preferences', {}))} 项")
                print(f"   - 项目记忆: {len(memory_ctx.get('project_memories', []))} 条")
                print(f"   - 相似任务: {len(memory_ctx.get('similar_tasks', []))} 个")
                print(f"   ✅ 上下文注入完成")
            else:
                print("\n⚠️ [Memory] 未检测到上下文记忆，使用默认配置")

            # 执行任务
            result = execute_task(task_type, payload, task_id, steps, events, context)

            # 写回成功结果
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

            # 通知 Node.js
            try:
                notify_url = f"{NODE_API_URL}/task/notify/{task_id}"
                print(f"\n📡 正在通知 Node.js: {notify_url}")

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
                    print(f"响应内容: {response.text}")
            except Exception as notify_error:
                print(f"⚠️ 通知 Node.js 失败: {notify_error}")
                print("   结果已保存在 Redis，但前端可能无法实时收到")

            clear_stop_flag(task_id)

        except Exception as e:
            is_cancelled = "取消" in str(e) or "cancel" in str(e).lower()

            if is_cancelled:
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
                    context=context,
                )

                print("\n" + "=" * 60)
                print("🛑 任务已被用户取消")
                print("=" * 60 + "\n")
            else:
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
                    context=context,
                )

                print("\n" + "=" * 60)
                print("任务失败，错误结果已写入 Redis:")
                print(TaskModel.pretty_print(error_result))
                print("=" * 60 + "\n")

            if result_key:
                redis.set(result_key, json.dumps(error_result))

            try:
                notify_url = f"{NODE_API_URL}/task/notify/{task_id}"
                print(f"\n📡 正在通知 Node.js (错误任务): {notify_url}")

                response = requests.post(
                    notify_url,
                    json=error_result,
                    headers={"Content-Type": "application/json"},
                    timeout=10,
                )

                if response.status_code == 200:
                    print("✅ Node.js 已成功接收错误通知，将推送给前端")
                else:
                    print(f"⚠️ Node.js 返回错误状态码: {response.status_code}")
            except Exception as notify_error:
                print(f"⚠️ 通知 Node.js 失败: {notify_error}")

            clear_stop_flag(task_id)

            if not is_cancelled:
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

                redis.lpush(dlq_key, json.dumps(dlq_item))

                print("\n" + "=" * 60)
                print("任务已写入死信队列:")
                print(TaskModel.pretty_print(dlq_item))
                print("=" * 60 + "\n")


if __name__ == "__main__":
    print("\n🚀 Qwen Worker v3.0 已启动")
    print(f"   · Worker ID: {WORKER_ID}")
    print(f"   · Node API: 已连接")
    print(f"   · 正在监听任务队列...\n")
    main_loop()
