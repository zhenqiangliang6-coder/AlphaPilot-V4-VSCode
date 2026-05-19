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
if python_worker_dir not in sys.path:
    sys.path.insert(0, python_worker_dir)

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
from agents.local_llm.personas import PERSONA_CONFIGS, get_persona_config
from intent_router import IntentRouter
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

BASE_CHAIN = ["analyze", "plan", "write", "refine", "test", "fix", "doc", "docstring", "profile"]

INTENT_CHAINS = {
    # ⭐ 完整工程链路（复杂任务）
    "write_code": ["analyze", "plan", "write", "refine", "test", "fix", "doc", "docstring"],
    
    # ⭐ 简化代码生成链路（简单任务，如排序函数、工具函数）
    "simple_code": ["write", "test"],
    
    # 文档生成
    "generate_doc": ["analyze", "plan", "write", "doc", "docstring"],
    
    # 代码解释
    "explain_code": ["analyze", "plan", "doc"],
    
    # 创意写作
    "creative_writing": ["analyze", "plan", "write", "refine"],
    
    # 闲聊
    "chat": ["analyze", "write"],
}


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
        applied = []
        failed = []
        for f in fileops:
            try:
                abspath = os.path.join(workspace_root, f.path)
                dirpath = os.path.dirname(abspath)
                if not os.path.exists(dirpath):
                    os.makedirs(dirpath, exist_ok=True)
                # 简单写入（覆盖）
                with open(abspath, "w", encoding="utf-8") as fh:
                    fh.write(f.content or "")
                applied.append(f)
            except Exception as e:
                failed.append({"file": f.path, "error": str(e)})
        return ApplyResult(success=(len(failed) == 0), applied=applied, failed=failed)

# 工厂函数
def get_local_worker_ability() -> LocalWorkerAbility:
    return LocalWorkerAbility()



def build_execution_chain(intent: str, prompt: str = None) -> list:
    """
    v3.2.1 修复：强制 Local Worker 只执行 write 步骤
    
    ⭐ 核心原则：
    - Local Worker 能力有限，禁止复杂执行链
    - 只执行 write，避免 test/refine/fix 导致的崩溃
    - Qwen Worker 保持原有逻辑不变
    """
    
    # ⭐ 关键修复：检测是否为 Local Worker
    worker_id = os.environ.get("WORKER_ID", "")
    is_local_worker = "local" in worker_id.lower() or "gemma" in worker_id.lower()
    
    if is_local_worker:
        # Local Worker：只执行 write
        print(f"\n💡 Local Worker 模式：强制使用简化执行链 [write]")
        return ["write"]
    
    # Qwen Worker：保持原有逻辑
    chain = INTENT_CHAINS.get(intent, DEFAULT_ENGINEERING_STEPS)
    
    # 智能简化：简单任务减少步骤
    is_simple_task = detect_simple_task(prompt)
    
    if is_simple_task:
        print(f"\n💡 检测到简单任务，使用简化执行链: write → test")
        return INTENT_CHAINS.get("simple_code", ["write", "test"])
    
    return chain


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
    Local LLM Worker v3.0 统一入口：
    - 处理 local_generate 任务
    - Intent Router + Persona + Execution Chain
    - 多步骤执行 + FileOps 全链路
    - 支持流式输出
    """
    
    # ⭐ 标准任务：local_generate
    if task_type != "local_generate":
        raise ValueError(f"不支持的任务类型：{task_type}")

    prompt = payload.get("prompt", "")
    
    if not prompt:
        raise ValueError("prompt 不能为空")

    # 1) 意图识别 + 人格选择
    intent, persona_type, _ = IntentRouter.detect_intent(prompt)
    persona_config = get_persona_config(persona_type)

    # 2) 构建执行链（⭐ 传入 prompt 以支持智能简化）
    execution_chain = build_execution_chain(intent, prompt)

    # 写入 meta
    context["meta"] = {
        "intent": intent,
        "persona": persona_type,
        "persona_config": persona_config,
        "execution_chain": execution_chain,
    }
    
    # ⭐ v3.2.2 关键修复：将用户原始 prompt 存入 context，供 write_step 使用
    context["user_query"] = prompt

    # 注入能力实例（行为契约实现），上层步骤可通过 context['_ability'] 使用
    try:
        context["_ability"] = get_local_worker_ability()
    except Exception:
        context["_ability"] = None

    print("\n🧠 Local LLM Worker v3.0 决策：")
    print(f"  意图: {intent}")
    print(f"  人格: {persona_config['name']} ({persona_config['icon']})")
    print(f"  执行链: {' → '.join(execution_chain)}")

    # 3) 如果外部未传入 steps，则根据执行链动态生成
    if not steps:
        steps.extend(create_steps_from_chain(execution_chain, prompt, persona_type, intent))
        print(f"\n📋 动态生成 {len(steps)} 个步骤 (意图: {intent})")

    # 4) Planner 兜底（可选）
    if not steps:
        # TODO: 实现 LLM 任务分解
        print("⚠️ 未实现 LLM 任务分解，跳过 Planner 步骤")
        pass

    # 5) 逐步执行（带取消检查 + 状态管理）
    for step in steps:
        try:
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
    last_output = steps[-1].get("output", {})
    return last_output.get("text", "")


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
            result = execute_task(task_type, payload, task_id, steps, events, context)

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
            if "_ability" in context:
                del context["_ability"]

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
