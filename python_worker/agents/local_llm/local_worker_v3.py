# -*- coding: utf-8 -*-
# agents/local_llm/local_worker_v3.py
# ---------------------------------------------------------
# Local LLM Worker v3.0
# - 基于 Qwen Worker v3.0 架构
# - 支持 LM Studio 本地模型
# ---------------------------------------------------------

import sys
import os
import time
import json
import threading
import traceback
import requests
from typing import Dict, Any, Optional
from dataclasses import dataclass
from typing import List, Callable

# 确保 python_worker 根目录在 sys.path 中
current_dir = os.path.dirname(os.path.abspath(__file__))
python_worker_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))
project_root = os.path.dirname(python_worker_dir)
if python_worker_dir not in sys.path:
    sys.path.insert(0, python_worker_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 绝对导入（避免相对导入超出顶层包的问题）
from worker_config import (
    NODE_API_URL,
    WORKER_ID,
    create_redis_client,
    get_worker_queue,
    check_stop_flag,
    clear_stop_flag,
    create_empty_context,
    stream_start,
    stream_chunk,
    stream_end,
    stream_error,
    create_event,
)
from TaskModel_v2 import TaskModel
from python_worker.protocol import PROTOCOL_VERSION, validate_worker_task
from python_worker.worker_runtime import prepare_worker_request, save_worker_memory
from agents.local_llm.personas import PERSONA_CONFIGS, get_persona_config
from intent_router import IntentRouter, requires_authorization_before_step
from collaboration_modes import apply_mode_to_persona, apply_mode_to_steps, enforce_file_operation_policy, prepare_collaboration_mode
from agents.local_llm.step_executor import execute_step
from agents.local_llm.local_api import call_local_llm
from file_ops import create_file_op

# 为了代码能跑通，这里需要初始化 redis 客户端
redis = create_redis_client()

# DLQ 名称
DLQ_NAME = "dlq"

# =========================================================
# v3.0：执行链定义（按意图动态裁剪）
# =========================================================

# =========================================================
# 能力层（Behavioral Ability）接口与本地适配器（占位实现）
# =========================================================


@dataclass
class FileOp:
    op_type: str
    path: str
    content: Optional[str] = None
    mode: Optional[str] = "text"
    meta: Dict[str, Any] = None


@dataclass
class FileOpsResult:
    file_ops: List[FileOp]
    raw_output: str
    diagnostics: Optional[Dict[str, Any]] = None


@dataclass
class ValidationResult:
    ok: bool
    errors: List[str]


@dataclass
class ApplyResult:
    success: bool
    applied: List[FileOp]
    failed: List[Dict[str, Any]]


class StreamHooks:
    def __init__(self, start: Callable = None, chunk: Callable = None, end: Callable = None, error: Callable = None):
        self.start = start
        self.chunk = chunk
        self.end = end
        self.error = error


class LocalLLMAdapter:
    """本地模型适配器（包装现有 call_local_llm）
    占位实现：stream=True/False 的封装，供能力层调用。
    """

    def call(self, prompt: str, stream: bool = False, task_id: str = None):
        # 直接调用现有实现；后续可替换为更复杂的重试/超时逻辑
        return call_local_llm(prompt, stream=stream, task_id=task_id)


class LocalWorkerAbility:
    """能力契约实现（行为层）。
    目前提供简单包装，behavioural contract 在此定义，具体实现可逐步增强。
    """

    def __init__(self, adapter: LocalLLMAdapter = None):
        self.adapter = adapter or LocalLLMAdapter()

    def generate_multi_file(self, prompt: str, task_id: str = None, opts: dict = None) -> FileOpsResult:
        raw = self.adapter.call(prompt, stream=False, task_id=task_id)
        # 占位解析：不尝试重写复杂解析逻辑，返回 raw 输出供上层或 write_step 解析
        return FileOpsResult(file_ops=[], raw_output=raw, diagnostics={"note": "parsing deferred to write_step"})

    def stream_generate(self, prompt: str, task_id: str, hooks: StreamHooks = None, opts: dict = None):
        # 简单的流封装：调用 adapter.call(stream=True)；实际流回调由 adapter 内部触发（如果支持）
        return self.adapter.call(prompt, stream=True, task_id=task_id)

    def validate_fileops(self, fileops: List[FileOp], workspace_root: str) -> ValidationResult:
        # 简单校验：路径安全与后缀白名单
        errors = []
        allowed = {".py", ".md", ".txt", ".json", ".yml", ".yaml"}
        for f in fileops:
            p = os.path.normpath(f.path)
            if os.path.isabs(p) or p.startswith(".."):
                errors.append(f"非法路径: {f.path}")
            _, ext = os.path.splitext(p)
            if ext and ext not in allowed:
                errors.append(f"不允许的后缀: {f.path}")
        return ValidationResult(ok=(len(errors) == 0), errors=errors)

    def apply_fileops(self, fileops: List[FileOp], workspace_root: str, options: dict = None) -> ApplyResult:
        raise RuntimeError(
            "Direct filesystem writes are disabled; file operations must be applied by the host policy layer."
        )

# 工厂函数
def get_local_worker_ability() -> LocalWorkerAbility:
    return LocalWorkerAbility()



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
):
    """
    Local LLM Worker v3.0 统一入口：
    - 处理 local_generate 任务
    - Intent Router + Persona + Execution Chain
    - 多步骤执行 + FileOps 全链路
    - 支持流式输出
    """
    
    # ⭐ 标准任务：local_generate
    if task_type != "local_generate":
        raise ValueError(f"不支持的任务类型：{task_type}")

    prepared = prepare_worker_request(
        payload, task_id, task_type, "Local LLM", protocol_metadata
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
        **prepared["meta"],
        "persona_config": persona_config,
        "execution_chain": execution_chain,
        "execution_plan": execution_plan,
        "collaboration_mode": mode,
        "model": "local",
    }
    
    # ⭐ v3.2.2 关键修复：将用户原始 prompt 存入 context，供 write_step 使用
    context["user_query"] = prompt

    context["_respond_call"] = _respond_call

    print("\n🧠 Local LLM Worker v3.0 决策：")
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
        # TODO: 实现 LLM 任务分解
        print("⚠️ 未实现 LLM 任务分解，跳过 Planner 步骤")
        pass

    # 5) 逐步执行（带取消检查 + 状态管理）
    for step in steps:
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

            # ⭐ v3.0：如果需要自定义 API 函数，通过 context 注入
            # Local LLM 使用 call_local_llm_wrapper 替代默认的 call_qwen
            context["_custom_api_func"] = lambda p: call_local_llm_wrapper(p, task_id)

            # ⭐ 对齐 Qwen Worker v2：直接调用 execute_step，不再传递 api_func 参数
            execute_step(task_id, step, events, context)

            # 清理临时注入的 api_func
            if "_custom_api_func" in context:
                del context["_custom_api_func"]

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
    return call_local_llm(full_prompt, stream=bool(task_id), task_id=task_id)


def call_local_llm_wrapper(prompt: str, task_id: str = None) -> str:
    """
    Local LLM API 调用包装器（支持流式输出）
    """
    from .local_api import call_local_llm
    return call_local_llm(prompt, stream=True, task_id=task_id)


# =========================================================
# 主循环：从 Redis 取任务 → 执行 → 写回结果
# =========================================================

def main_loop():
    dlq_key = DLQ_NAME
    # 使用 get_worker_queue 替代 QUEUE_NAME
    queue_name = get_worker_queue("local_generate")
    print(f"📡 Local LLM Worker v3.0 监听队列: {queue_name}")

    while True:
        # ⭐ 初始化变量，避免异常处理时未定义
        task_id = None
        task_type = None
        started_at = None
        retry_count = 0
        steps = []
        events = []
        context = create_empty_context()
        result_key = None
        
        try:
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

            # 只处理 local_ 开头的任务
            if task_type and not task_type.startswith("local_"):
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

            # 执行任务
            result = execute_task(
                task_type, payload, task_id, steps, events, context,
                protocol_metadata={
                    "protocol_version": task.get("protocol_version"),
                    "trace_id": task.get("trace_id"),
                },
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

            # write_step 负责生成并注入 final_file_ops（包含严格的自然语言解析），此处不再重复解析

            # ⭐ v3.2.1 修复：清理 context 中无法序列化的对象
            if "_ability" in context:
                del context["_ability"]
                print("[INFO] 已清理 context['_ability'] (LocalWorkerAbility 不可序列化)")

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

            # ⭐ v3.2.1 修复：清理 context 中无法序列化的对象（错误分支）
            context.pop("_ability", None)
            context.pop("_respond_call", None)

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
    print("\n🚀 Local LLM Worker v3.0 已启动")
    print(f"   · Worker ID: {WORKER_ID}")
    print(f"   · Node API: 已连接")
    print(f"   · 正在监听任务队列...\n")
    main_loop()
