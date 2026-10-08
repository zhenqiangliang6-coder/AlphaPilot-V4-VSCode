# -*- coding: utf-8 -*-
# modelscope_worker_v3.py
# ---------------------------------------------------------
# ModelScope Worker v3.0 — 世界级执行链架构版
# - Intent Router：意图识别
# - Persona Engine：执行链人格（engineer/creator/conversational）
# - Execution Chain：analyze → plan → write → refine → test → fix → doc → docstring → profile
# - FileOps：多文件协议 v3.0（FILE/TEST/DOC/META/DEPENDS）
# - 与现有 step_executor 完全兼容（最小侵入升级）
# ---------------------------------------------------------

import json
import os
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
from ...intent_router import IntentRouter, requires_authorization_before_step
from ...collaboration_modes import apply_mode_to_persona, apply_mode_to_steps, enforce_file_operation_policy, prepare_collaboration_mode
from .step_executor.execute_step import execute_step
from .personas import get_persona_config
from ...TaskModel_v2 import TaskModel
from ...protocol import PROTOCOL_VERSION, validate_worker_task
from ...worker_runtime import prepare_worker_request, save_worker_memory
from ...worker_respond_step import run_respond_step
from .modelscope_api import call_modelscope, call_modelscope_stream

CHECKPOINT_VERSION = 1
CHECKPOINT_KEY_PREFIX = "modelscope_worker_v3:checkpoint:"
CHECKPOINT_TTL_SECONDS = max(
    60, int(os.getenv("MODELSCOPE_CHECKPOINT_TTL_SECONDS", "604800"))
)


def _checkpoint_key(task_id: str) -> str:
    return f"{CHECKPOINT_KEY_PREFIX}{task_id}"


def save_worker_checkpoint(
    task_id: str,
    task_type: str,
    steps: list,
    events: list,
    context: dict,
) -> None:
    """Persist the completed execution boundary so a redelivered task can resume."""
    checkpoint_context = {
        key: value for key, value in context.items() if not key.startswith("_")
    }
    checkpoint = {
        "version": CHECKPOINT_VERSION,
        "task_id": task_id,
        "task_type": task_type,
        "saved_at": int(time.time() * 1000),
        "steps": steps,
        "events": events,
        "context": checkpoint_context,
    }
    redis.set(
        _checkpoint_key(task_id),
        json.dumps(checkpoint, ensure_ascii=False),
        ex=CHECKPOINT_TTL_SECONDS,
    )


def load_worker_checkpoint(task_id: str, task_type: str):
    """Load and validate a saved task boundary, if one exists."""
    raw_checkpoint = redis.get(_checkpoint_key(task_id))
    if not raw_checkpoint:
        return None
    if isinstance(raw_checkpoint, bytes):
        raw_checkpoint = raw_checkpoint.decode("utf-8")

    checkpoint = json.loads(raw_checkpoint)
    if (
        checkpoint.get("version") != CHECKPOINT_VERSION
        or checkpoint.get("task_id") != task_id
        or checkpoint.get("task_type") != task_type
        or not isinstance(checkpoint.get("steps"), list)
        or not isinstance(checkpoint.get("events"), list)
        or not isinstance(checkpoint.get("context"), dict)
    ):
        raise ValueError(f"任务 {task_id} 的 ModelScope 进度检查点无效")
    return checkpoint


def clear_worker_checkpoint(task_id: str) -> None:
    redis.delete(_checkpoint_key(task_id))


# =========================================================
# v3.0：执行链定义（按意图动态裁剪）
# =========================================================

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
        "respond": {"type": "respond", "input": {"prompt": prompt}},
        "workspace": {
            "type": "workspace",
            "input": {"prompt": "执行已明确请求的工作区检查和 Python 环境操作"}
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

def execute_task(
    task_type: str,
    payload: dict,
    task_id: str,
    steps: list,
    events: list,
    context: dict,
    protocol_metadata: dict = None,
    checkpoint_callback=None,
):
    """
    ModelScope Worker v3.0 统一入口：
    - 只处理 modelscope_generate 任务
    - Intent Router + Persona + Execution Chain
    - 多步骤执行 + FileOps 全链路
    """
    if task_type != "modelscope_generate":
        raise ValueError(f"不支持的任务类型：{task_type}")

    prepared = prepare_worker_request(
        payload, task_id, task_type, "ModelScope", protocol_metadata
    )
    prompt = prepared["prompt"]
    execution_plan = prepared["execution_plan"]
    intent = execution_plan["intent"]
    persona_type = execution_plan["persona"]
    requested_mode = payload.get("collaboration_mode")
    if intent == "mentor_explain":
        requested_mode = "teacher"
    mode, prompt, execution_chain = prepare_collaboration_mode(
        requested_mode,
        prompt,
        execution_plan["execution_chain"],
        preserve_chain=intent in {"mentor_explain", "external_git"},
        intent=intent,
    )
    if intent == "workspace_maintenance" and not prepared["meta"]["workspace_scan"]["fixable_issue_count"]:
        execution_chain = [step for step in execution_chain if step != "fix"]
    execution_plan["execution_chain"] = list(execution_chain)
    persona_config = apply_mode_to_persona(get_persona_config(persona_type), mode)

    # 写入 meta
    context["meta"] = {
        **context.get("meta", {}),
        **prepared["meta"],
        "persona_config": persona_config,
        "execution_chain": execution_chain,
        "execution_plan": execution_plan,
        "collaboration_mode": mode,
        "model": "modelscope",
    }
    context["_respond_call"] = _respond_call
    if checkpoint_callback:
        context["_checkpoint_callback"] = checkpoint_callback

    print("\n🧠 ModelScope Worker v3.0 决策：")
    print(f"  意图: {intent}")
    print(f"  人格: {persona_config['name']} ({persona_config['icon']})")
    print(f"  执行链: {' → '.join(execution_chain)}")

    # 3) 如果外部未传入 steps，则根据执行链动态生成
    if not steps:
        steps.extend(create_steps_from_chain(execution_chain, prompt, persona_type, intent))
        print(f"\n📋 动态生成 {len(steps)} 个步骤 (意图: {intent})")
    apply_mode_to_steps(steps, mode)

    # 4) Planner 兜底（可选）
    if not steps:
        plan_steps = llm_decompose_task(prompt)
        steps.extend(plan_steps)

    # 5) 逐步执行（带取消检查 + 状态管理）
    for step in steps:
        if step.get("status") == "completed":
            continue
        try:
            if requires_authorization_before_step(execution_plan, step.get("type", "")):
                step["status"] = "awaiting_authorization"
                step["output"] = {
                    "text": "验证步骤需先向用户展示完整测试命令并取得确认；当前任务未运行该步骤。",
                    "proposed_command": context["meta"].get("proposed_test_command"),
                }
                context["meta"].setdefault("deferred_steps", []).append(step.get("type"))
                context["meta"].setdefault("authorization_requests", []).append({
                    "type": "test",
                    "command": context["meta"].get("proposed_test_command"),
                    "status": "awaiting_user_confirmation",
                })
                continue

            if check_stop_flag(task_id):
                step["status"] = "failed"
                step["output"] = {"text": "任务已被用户取消"}
                raise Exception("任务已被用户取消")

            step["status"] = "running"

            # 交给通用 step_executor.execute_step
            execute_step(task_id, step, events, context)
            if step.get("output", {}).get("llm_success") is False:
                raise RuntimeError(
                    f"{step.get('type')} 步骤的 ModelScope 调用未成功"
                )

            step["status"] = "completed"
            if checkpoint_callback:
                checkpoint_callback()

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
    enforce_file_operation_policy(context, mode, steps=steps, events=events)
    if any(operation.get("op") == "delete" for operation in context.get("final_file_ops", [])):
        context["meta"].setdefault("authorization_requests", []).append({
            "type": "delete",
            "paths": [
                operation.get("path")
                for operation in context.get("final_file_ops", [])
                if operation.get("op") == "delete"
            ],
            "status": "awaiting_host_policy",
        })
    if context["meta"].get("authorization_requests"):
        context["meta"]["execution_state"] = "awaiting_authorization"
    last_output = steps[-1].get("output", {})
    return last_output.get("text", "")


def _respond_call(prompt, persona_config, task_id):
    full_prompt = (
        f"{persona_config.get('system_prompt', '')}\n\n---\n\n{prompt}"
        if persona_config else prompt
    )
    return call_modelscope_stream(full_prompt) if task_id else call_modelscope(full_prompt)


# =========================================================
# 主循环：从 Redis 取任务 → 执行 → 写回结果
# =========================================================

def main_loop():
    dlq_key = "dlq"
    queue_name = get_worker_queue("modelscope_generate")
    print(f"📡 ModelScope Worker v3.0 监听队列: {queue_name}")

    while True:
        try:
            result_key = None

            task_json = redis.rpop(queue_name)
            if not task_json:
                time.sleep(2)
                continue

            task = validate_worker_task(json.loads(task_json))

            print("\n" + "=" * 60)
            print("收到任务:")
            print(TaskModel.pretty_print(task))
            print("=" * 60 + "\n")

            task_id = task["task_id"]
            task_type = task.get("task_type") or task.get("type")
            payload = task["payload"]

            # 只处理 modelscope_generate
            if task_type and not task_type.startswith("modelscope_"):
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
            checkpoint = load_worker_checkpoint(task_id, task_type)
            if checkpoint:
                steps = checkpoint["steps"]
                events = checkpoint["events"]
                context = checkpoint["context"]
                completed_steps = sum(
                    step.get("status") == "completed" for step in steps
                )
                print(
                    f"♻️ 恢复任务检查点: {completed_steps}/{len(steps)} 个步骤已完成"
                )
            context.setdefault("final_file_ops", [])

            def persist_progress():
                save_worker_checkpoint(task_id, task_type, steps, events, context)

            # 执行任务
            result = execute_task(
                task_type, payload, task_id, steps, events, context,
                protocol_metadata={
                    "protocol_version": task.get("protocol_version"),
                    "trace_id": task.get("trace_id"),
                },
                checkpoint_callback=persist_progress,
            )
            save_worker_memory(
                context.get("meta", {}).get("memory_user_id"),
                task_id,
                task_type,
                context.get("meta", {}).get("intent", "unknown"),
                result,
                steps,
                context,
            )
            context.pop("_respond_call", None)
            context.pop("_checkpoint_callback", None)

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
            if task.get("protocol_version") == PROTOCOL_VERSION:
                result_data["protocol_version"] = task["protocol_version"]
                result_data["trace_id"] = task["trace_id"]

            redis.set(result_key, json.dumps(result_data))
            try:
                clear_worker_checkpoint(task_id)
            except Exception as checkpoint_error:
                print(f"⚠️ 清理 ModelScope 进度检查点失败: {checkpoint_error}")

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
            if "context" in locals() and isinstance(context, dict):
                context.pop("_respond_call", None)
                context.pop("_checkpoint_callback", None)
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
    print("\n🚀 ModelScope Worker v3.0 已启动")
    print(f"   · Worker ID: {WORKER_ID}")
    print(f"   · Node API: 已连接")
    print(f"   · 正在监听任务队列...\n")
    main_loop()
