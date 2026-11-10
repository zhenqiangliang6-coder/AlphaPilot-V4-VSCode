# -*- coding: utf-8 -*-
# qwen_worker_v3.py
# ---------------------------------------------------------
# Qwen Worker v3.0 — 世界级执行链架构版
# - Intent Router：意图识别
# - Persona Engine：执行链人格（engineer/creator/conversational）
# - Execution Chain：analyze → plan → write → refine → test → fix → doc → docstring → profile
# - FileOps：多文件协议 v3.0（FILE/TEST/DOC/META/DEPENDS）
# - ⭐ Memory Integration：记忆中枢集成（任务前注入上下文，任务后保存洞察）
# - 与现有 step_executor 完全兼容（最小侵入升级）
# ---------------------------------------------------------

import json
import os
import time
import traceback
import requests
from pathlib import Path

from ...worker_config import (
    redis,
    WORKER_ID,
    create_empty_context,
    check_stop_flag,
    clear_stop_flag,
    get_worker_queue,
    NODE_API_URL,
    stream_chunk,
    stream_start,
)

from ...planner import llm_decompose_task
from ...intent_router import IntentRouter, requires_authorization_before_step
from ...intent_router._data import INTENT_TO_PERSONA
from ...protocol import PROTOCOL_VERSION, TaskProtocolError, validate_worker_task
from ...skills import route_skill
from ...capability_executor import resolve_and_execute_capabilities
from ...context_builder import inspect_python_project, read_project_context, read_requested_python_files, search_project_files
from ...collaboration_modes import apply_mode_to_persona, apply_mode_to_steps, enforce_file_operation_policy, prepare_collaboration_mode
from .step_executor import execute_step
from .personas import get_persona_config
from ...TaskModel_v2 import TaskModel
from ...task_state_contract import (  # G2.2: 契约常量
    TASK_STATE_PENDING,
    TASK_STATE_RUNNING,
    TASK_STATE_WAITING_AUTHORIZATION,
    TASK_STATE_COMPLETED,
    TASK_STATE_FAILED,
    STEP_STATE_PENDING,
    STEP_STATE_RUNNING,
    STEP_STATE_COMPLETED,
    STEP_STATE_FAILED,
    STEP_STATE_AWAITING_AUTHORIZATION,
    STEP_STATE_SKIPPED,
    transition_is_legal,
    guard_not_terminal_state,
    TASK_STATE_TO_LEGACY_STATUS,
    AUDIT_EVENT_TASK_STARTED,
    AUDIT_EVENT_TASK_COMPLETED,
    AUDIT_EVENT_TASK_FAILED,
    AUDIT_EVENT_TASK_AWAITING_AUTHORIZATION,
    AUDIT_EVENT_STEP_STARTED,
    AUDIT_EVENT_STEP_COMPLETED,
    AUDIT_EVENT_STEP_FAILED,
    AUDIT_EVENT_STEP_SKIPPED,
    ERROR_CODE_TASK_CANCELLED,
    ERROR_CODE_TASK_PROTOCOL_ERROR,
    ERROR_CODE_MODEL_CALL_ERROR,
    ERROR_CODE_CONTRACT_VIOLATION,
    ERROR_CODE_STEP_EXECUTION_ERROR,
    validate_result_contract,
    ContractViolationError,
    EvidenceGate,
    EvidenceGateBlocked,                # Phase F: 准入阻断
    ERROR_CODE_EVIDENCE_GATE_BLOCKED,   # Phase F: 准入错误码
    validate_workspace_evidence,        # Phase F: 统一证据验证
    validate_architecture_evidence,     # G5.1: 架构证据验证
)
from ...file_ops import cleanup_previous_generated, track_generated_files, create_file_op
from ...memory_integration import project_memory_user_id
from ..vision_api import has_vision_support

# ⭐ 记忆集成层（延迟导入，避免循环依赖）
try:
    from ...memory_integration import (
        build_memory_context,
        enhance_prompt_with_memory,
        save_task_memories
    )
    MEMORY_ENABLED = True
except ImportError as e:
    print(f"[WARN] 记忆集成层导入失败: {e}")
    MEMORY_ENABLED = False

# ⭐ 短期记忆闭环（P3）：复用 worker_runtime 的读端/写端接口
try:
    from ...worker_runtime import (
        inject_conversation_memory,
        save_conversation_memory,
        _extract_conversation_id,
    )
    _SHORT_TERM_MEMORY_ENABLED = True
except ImportError as e:
    print(f"[WARN] 短期记忆闭环导入失败: {e}")
    inject_conversation_memory = None
    save_conversation_memory = None
    _extract_conversation_id = None
    _SHORT_TERM_MEMORY_ENABLED = False


# =========================================================
# v3.0：统一任务执行入口（Orchestrator）
# =========================================================
#
# 功能模块拆分：
#   execution_chain.py   — 执行链定义 + 步骤构建
#   compound_executor.py — G8.0 复合阶段
#   task_context.py      — 工作区扫描 + 证据收集 + 能力注入
#   post_analyzer.py     — Post-analyze 重决策
#   step_runner.py       — 步骤执行循环 + 收尾
#
# qwen_worker_v2.py     — 本文档：Orchestrator + main_loop
# =========================================================

from .execution_chain import build_execution_chain, create_steps_from_chain
from .compound_executor import exec_compound_phases
from .task_context import (
    scan_workspace_for_intent,
    resolve_capabilities_and_skill as _resolve_and_inject_capabilities,
    apply_skill_and_mode as _apply_skill_and_mode,
    collect_workspace_evidence,
)
from .post_analyzer import run_post_analyze
from .step_runner import run_execution_loop, finalize_task


def _derive_conversation_outcome(steps) -> str:
    """从步骤推导真实执行结果，失败任务绝不误标 success（安全红线，与 worker_runtime 一致）。"""
    return (
        "failed"
        if any(
            isinstance(s, dict) and (
                s.get("type") == "error"
                or s.get("error") not in (None, "", False)
            )
            for s in steps or ()
        )
        else "success"
    )


def execute_task(
    task_type: str,
    payload: dict,
    task_id: str,
    steps: list,
    events: list,
    context: dict,
    protocol_metadata: dict = None,
):
    if task_type != "qwen_generate":
        raise ValueError(f"不支持的任务类型：{task_type}")

    prompt = payload.get("prompt", "")
    if not prompt and not has_vision_support(payload):
        raise ValueError("prompt 不能为空（无图片时）")

    # ── 记忆集成 ──
    user_id = project_memory_user_id(
        payload.get("project_path") or payload.get("workspace_path")
    )
    memory_ctx = None
    original_prompt = prompt

    _intent_prompt = prompt
    if not prompt.strip() and has_vision_support(payload):
        _intent_prompt = "分析上传的图片并根据图片内容处理（报错则修复、设计图则生成代码、文档则解释说明）"

    if MEMORY_ENABLED and user_id:
        try:
            memory_ctx = build_memory_context(user_id, task_id, prompt,
                                               workspace_path=payload.get("workspace_path"))
            if memory_ctx.has_memory:
                prompt = enhance_prompt_with_memory(prompt, memory_ctx)
                print(f"\n🧠 [MEMORY] 已为任务 {task_id} 注入记忆上下文")
        except Exception as e:
            print(f"\n⚠️ [MEMORY] 记忆注入失败，继续执行: {e}")

    # ── P3 conversation_id 预提取：从 payload 三路径提取并预注入 context（读端注入依赖此值） ──
    if _extract_conversation_id:
        _payload_cid = _extract_conversation_id(payload)
        if _payload_cid and not context.get("meta", {}).get("conversation_id"):
            context.setdefault("meta", {})["conversation_id"] = _payload_cid

    # ── P3 短期记忆注入：读回上一轮会话历史（conversation_id 已在上方预注入） ──
    if _SHORT_TERM_MEMORY_ENABLED:
        _conv_id = context.get("meta", {}).get("conversation_id")
        if _conv_id:
            try:
                prompt = inject_conversation_memory(prompt, _conv_id)
                print(f"\n[Conversation] 短期记忆注入完成: {_conv_id}")
            except Exception as e:
                print(f"\n[Conversation] 短期记忆注入降级: {e}")

    # ── 意图识别 + G8.0 复合检测 ──
    detected_intent, detected_persona, detected_chain = IntentRouter.detect_intent(_intent_prompt)

    compound_plan = IntentRouter.detect_intent_multi(_intent_prompt)
    if compound_plan.is_compound:
        print(f"\n🔀 [G8.0] 复合请求检测: {len(compound_plan.phases)} 阶段")
        for i_ph, ph in enumerate(compound_plan.phases):
            print(f"   Phase {i_ph + 1}: [{ph.type}] {ph.prompt[:60]}")
    else:
        compound_plan = None

    # ── 工作区扫描（按意图分派）──
    scan_result = scan_workspace_for_intent(
        detected_intent, payload, task_id, original_prompt, prompt
    )
    prompt = scan_result["prompt"]
    project_context = scan_result["project_context"]
    project_context_files = scan_result["project_context_files"]
    source_files = scan_result["source_files"]
    workspace_scan = scan_result["workspace_scan"]
    workspace_report = scan_result["workspace_report"]

    # ── 执行计划 + Skill 路由 ──
    execution_plan = IntentRouter.plan_request(
        original_prompt,
        workspace_available=bool(project_context_files or workspace_scan),
        source_files_available=bool(source_files),
        worker="qwen",
        detected_intent=detected_intent,
        detected_persona=detected_persona,
        detected_chain=detected_chain,
    )
    selected_skill = route_skill(original_prompt)

    # ── 能力解析 + Skill 注入 ──
    capability_prompt = _resolve_and_inject_capabilities(selected_skill, context, payload)
    prompt += capability_prompt

    if selected_skill:
        prompt = (
            f"{prompt}\n\n[AlphaPilot Skill: {selected_skill.id} "
            f"v{selected_skill.version}]\n{selected_skill.guidance}"
        )

    intent = execution_plan["intent"]
    persona_type = execution_plan["persona"]
    requested_mode = payload.get("collaboration_mode")

    # ── Skill + 协作模式 + 链过滤 ──
    raw_chain = build_execution_chain(intent, original_prompt)
    mode, prompt, execution_chain = _apply_skill_and_mode(
        prompt, intent, original_prompt, raw_chain,
        selected_skill, requested_mode, payload, workspace_scan,
    )

    has_vision = has_vision_support(payload)
    if has_vision:
        execution_chain = ["vision_analysis"] + [s for s in execution_chain if s != "vision_analysis"]
    execution_plan["execution_chain"] = list(execution_chain)

    # ── Phase D: 工作区证据收集 ──
    workspace_evidence, evidence_search_hits, evidence_pc, evidence_pcf = \
        collect_workspace_evidence(
            payload, workspace_scan, project_context_files, source_files,
            original_prompt, execution_chain,
        )
    if evidence_pc:
        project_context = evidence_pc
    if evidence_pcf:
        project_context_files = evidence_pcf

    persona_config = apply_mode_to_persona(get_persona_config(persona_type), mode)

    # ── 写入 meta ──
    _existing = context.get("meta", {})
    context["meta"] = {
        "protocol_version": (protocol_metadata or {}).get("protocol_version"),
        "trace_id": (protocol_metadata or {}).get("trace_id"),
        "intent": intent,
        "persona": persona_type,
        "persona_config": persona_config,
        "execution_chain": execution_chain,
        "execution_plan": execution_plan,
        "user_request": original_prompt,
        "proposed_test_command": scan_result.get("proposed_test_command"),
        "workspace_path": workspace_scan["root"] if workspace_scan else payload.get("workspace_path"),
        "workspace_scan": workspace_scan,
        "workspace_report": workspace_report,
        "project_context_files": project_context_files,
        "source_files": source_files,
        "workspace_evidence": workspace_evidence,
        "evidence_search_hits": evidence_search_hits,
        "_capability_results": context.get("_capability_results", {}),
        "architecture_evidence": context.get("_capability_results", {}).get("arch.analyze"),
        "collaboration_mode": mode,
        "has_memory": memory_ctx.has_memory if memory_ctx else False,
        "memory_user_id": user_id,
        "skill": selected_skill.as_dict() if selected_skill else None,
        "auto_repair_on_test_failure": (
            IntentRouter.requests_test_failure_repair(original_prompt)
        ),
        # P2: 保留 conversation_id（由 main_loop 在 execute_task 前注入）
        "conversation_id": _existing.get("conversation_id"),
    }
    _inject_task_context_meta(context, payload, original_prompt)

    # ── 日志输出 ──
    print("\n🧠 Qwen Worker v3.0 决策：")
    print(f"  意图: {intent}")
    print(f"  人格: {persona_config['name']} ({persona_config['icon']})")
    print(f"  执行链: {' → '.join(execution_chain)}")
    if task_id:
        stream_chunk(
            task_id,
            f"自动识别为 {intent}（{persona_config['name']}），将执行：{' → '.join(execution_chain)}。\n",
            phase="routing", channel="reasoning",
        )
    if memory_ctx and memory_ctx.has_memory:
        print(f"  🧠 [MEMORY] 已注入记忆上下文 ({len(memory_ctx.memory_context)} 字符)")

    # ── v3.2 自清理 ──
    ws_root = context["meta"].get("workspace_path", "")
    if ws_root and intent in ("write_code", "fix_code", "refactor", "workspace_maintenance"):
        cleanup_previous_generated(redis, ws_root, context["final_file_ops"])

    # ── 构建步骤 ──
    if not steps:
        steps.extend(create_steps_from_chain(execution_chain, prompt, persona_type, intent))
        print(f"\n📋 动态生成 {len(steps)} 个步骤 (意图: {intent})")
    apply_mode_to_steps(steps, mode)

    if has_vision:
        _inject_vision_into_steps(steps, payload, task_type)

    # ── v4.4 Vision: vision_analysis 一等公民先行执行 ──
    if has_vision:
        _run_vision_step(steps, task_id, events, context)

    # ── v4.0 Post-analyze 链重决策 ──
    intent, persona_type, persona_config, execution_chain = run_post_analyze(
        steps, task_id, events, context,
        intent, persona_type, persona_config, execution_plan,
        prompt, original_prompt, payload, task_type, mode, selected_skill,
        has_vision, execution_chain,
    )

    # ── Planner 兜底 ──
    if not steps:
        steps.extend(llm_decompose_task(prompt))

    # ── Planning Contract 影子验证 ──
    _validate_plan_shadow(execution_plan, context)

    # ── 步骤执行循环 ──
    run_execution_loop(steps, execution_plan, task_id, events, context, intent, mode)

    # ── G8.0: 复合阶段 ──
    if compound_plan and compound_plan.is_compound:
        exec_compound_phases(
            compound_plan,
            execution_plan,
            task_id,
            events,
            context,
        )

    # ── 收尾必须在所有阶段之后：聚合 FileOps/授权并最后标记终止 ──
    last_output_text = finalize_task(context, steps, events, mode, intent, payload, task_id)

    return last_output_text


def _inject_task_context_meta(context: dict, payload: dict, original_prompt: str):
    task_context = payload.get("context")
    if not isinstance(task_context, dict):
        return
    meta = context.setdefault("meta", {})
    meta["task_goal"] = task_context.get("task_goal", original_prompt)
    meta["repair_rounds"] = int(task_context.get("repair_rounds", 0) or 0)
    prior_changed_files = task_context.get("prior_changed_files", [])
    if isinstance(prior_changed_files, list):
        meta["prior_changed_files"] = [
            f for f in prior_changed_files if isinstance(f, str) and f
        ]
    approved_command = task_context.get("authorized_test_command")
    if isinstance(approved_command, str) and approved_command.strip():
        meta["authorized_test_command"] = approved_command.strip()
        meta["proposed_test_command"] = approved_command.strip()
    meta["auto_repair_on_test_failure"] = (
        task_context.get("auto_repair_on_test_failure") is True
    )


def _inject_vision_into_steps(steps: list, payload: dict, task_type: str):
    for step in steps:
        if step.get("type") == "vision_analysis":
            step["input"]["images"] = payload.get("images", [])
            step["input"]["model_type"] = task_type
            step["input"]["workspace_path"] = payload.get("workspace_path", os.getcwd())
            break


def _run_vision_step(steps: list, task_id: str, events: list, context: dict):
    _vision_idx = next(
        (i for i, s in enumerate(steps) if s.get("type") == "vision_analysis"), -1
    )
    if _vision_idx < 0:
        return
    vision_step = steps.pop(_vision_idx)
    vision_step["status"] = STEP_STATE_RUNNING
    try:
        execute_step(task_id, vision_step, events, context)
        vision_step["status"] = STEP_STATE_COMPLETED
        context.setdefault("intermediate_results", []).append({
            "type": "vision_analysis",
            "text": vision_step.get("output", {}).get("text", ""),
            "image_count": vision_step.get("output", {}).get("image_count", 0),
            "elapsed_ms": vision_step.get("output", {}).get("elapsed_ms", 0),
            "llm_success": True,
        })
    except Exception as _ve:
        print(f"[Vision] ⚠️ vision_analysis 执行失败: {_ve}")
        vision_step["status"] = STEP_STATE_FAILED
        steps.insert(0, vision_step)


def _validate_plan_shadow(execution_plan: dict, context: dict):
    try:
        from intent_router._plan_validator import validate_plan_fields
        vr = validate_plan_fields(execution_plan)
        context["meta"]["_plan_validation"] = vr.to_dict()
        if not vr.valid:
            print(f"\n⚠️  [Planning Contract] 执行计划校验警告 ({len(vr.errors)} 问题):")
            for e in vr.errors:
                print(f"    - {e}")
        for w in vr.warnings:
            print(f"    ⚡ {w}")
    except Exception as _pv_err:
        print(f"[WARN] 计划影子验证异常: {_pv_err}")


# =========================================================
# G8: 多 Worker 智能编排 — 入口检测
# =========================================================

def _try_orchestrate(prompt: str, task_id: str, task: dict):
    """在主循环中检测是否需要多 Worker 编排。

    调用 Orchestrator.analyze() 进行 LLM 多语言分析。
    如果检测到多语言/多项目需求，自动拆解 → 并行分发
    → 聚合结果，返回完整的 orchestrationResult。
    如果是单语言请求或编排失败，返回 None（走正常路径）。

    Args:
        prompt: 用户原始输入
        task_id: 当前任务 ID
        task: 完整任务字典（含 meta/context）

    Returns:
        orchestrationResult dict 或 None
    """
    if not prompt or not isinstance(prompt, str) or len(prompt.strip()) < 10:
        return None

    try:
        from orchestrator import Orchestrator
    except ImportError:
        return None

    if not Orchestrator.ENABLED:
        return None

    print(f"\n🔍 [G8 Orchestrator] 检测是否为多语言/多项目需求...")
    orch = Orchestrator(redis)

    try:
        plan = orch.analyze(prompt)
    except Exception as e:
        print(f"   ⚠️ [G8 Orchestrator] analyze 异常: {e}，降级单 Worker")
        return None

    if not plan or not plan.is_multi_worker:
        if plan:
            print(f"   → 单语言请求 ({plan.languages})，走正常路径")
        else:
            print(f"   → 单语言/非编排请求，走正常路径")
        return None

    print(f"\n{'=' * 60}")
    print(f"🔀 [G8 Orchestrator] 多 Worker 编排启动")
    print(f"   · 编排 ID: {plan.orchestration_id}")
    print(f"   · 策略: {plan.strategy}")
    print(f"   · 语言: {plan.languages}")
    print(f"   · 子任务: {len(plan.subtasks)}")
    print(f"{'=' * 60}")

    try:
        result = orch.execute(plan)
        # 注入原始 task_id 以兼容结果管道
        result["task_id"] = task_id
        return result
    except Exception as e:
        print(f"   ⚠️ [G8 Orchestrator] execute 异常: {e}，降级单 Worker")
        traceback.print_exc()
        return None


# =========================================================
# 主循环：从 Redis 取任务 → 执行 → 写回结果
# =========================================================

def main_loop():
    dlq_key = "dlq"
    queue_name = get_worker_queue("qwen_generate")
    print(f"📡 Qwen Worker v3.0 监听队列: {queue_name}")

    while True:
        # ⭐ 初始化变量，避免异常处理时未定义
        task_id = None
        task_type = None
        started_at = None
        retry_count = 0
        steps = []
        events = []
        task = {}
        context = create_empty_context()
        result_key = None
        current_task_state = TASK_STATE_PENDING  # G2.2: 转换验证跟踪
        
        try:
            task_json = redis.rpop(queue_name)
            if not task_json:
                time.sleep(2)
                continue

            task = json.loads(task_json)
            task_id = task.get("task_id")
            task_type = task.get("task_type") or task.get("type")
            task = validate_worker_task(task)

            print("\n" + "=" * 60)
            print("收到任务:")
            print(TaskModel.pretty_print(task))
            print("=" * 60 + "\n")

            payload = task["payload"]

            # 只处理 qwen_generate
            if task_type and not task_type.startswith("qwen"):
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

            # G2.2 Inject 1: 任务开始执行 → task_state → RUNNING
            current_task_state = TASK_STATE_PENDING
            if not transition_is_legal(current_task_state, TASK_STATE_RUNNING):
                raise ContractViolationError(
                    f"非法 task state 转换: {current_task_state} → {TASK_STATE_RUNNING}"
                )
            current_task_state = TASK_STATE_RUNNING
            events.append({
                "event": AUDIT_EVENT_TASK_STARTED,
                "task_id": task_id,
                "sequence": len(events) + 1,
                "timestamp": int(time.time() * 1000),
                "idempotency_key": f"{task_id}:{AUDIT_EVENT_TASK_STARTED}:{len(events)}",
            })
            
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
                print("\n⚠️ [Task Context] 任务未携带预置上下文（无前端注入），将仅依赖内存中枢检索")

            # P2: conversation_id 多轮连续性 — 复用 worker_runtime 三路径提取（顶层 / task_context / context）
            if _extract_conversation_id:
                conversation_id = _extract_conversation_id(payload)
            else:
                payload_task_ctx = payload.get("task_context", {})
                conversation_id = payload_task_ctx.get("conversation_id") if isinstance(payload_task_ctx, dict) else None
            if conversation_id:
                context.setdefault("meta", {})["conversation_id"] = conversation_id
                print(f"\n🔄 [Conversation] 多轮对话 ID: {conversation_id}")
            else:
                print(f"\n⚠️ [Conversation] 未携带 conversation_id，此轮任务独立执行")

            # 执行任务
            # ── G8: 多 Worker 智能编排入口 ──
            prompt = payload.get("prompt", "")
            orchestrated_result = _try_orchestrate(prompt, task_id, task)

            if orchestrated_result:
                # 编排器已全权处理（拆解 → 并行分发 → 聚合），跳过正常执行路径
                result_key = f"task_result:{task_id}"
                safe_result = TaskModel.normalize_for_serialization(orchestrated_result)
                redis.set(result_key, json.dumps(safe_result, ensure_ascii=False))

                # 通知 Node.js
                try:
                    requests.post(
                        f"{NODE_API_URL}/task/notify/{task_id}",
                        json=safe_result,
                        headers={"Content-Type": "application/json"},
                        timeout=15,
                    )
                except Exception:
                    pass

                print(f"\n🔀 [G8 Orchestrator] 编排完成 → 结果已写入 {result_key}")
                continue

            result = execute_task(
                task_type,
                payload,
                task_id,
                steps,
                events,
                context,
                protocol_metadata={
                    "protocol_version": task.get("protocol_version"),
                    "trace_id": task.get("trace_id"),
                },
            )

            # ⭐ 防御：execute_task 异常路径可能丢失 context 或 meta
            if context is None:
                context = create_empty_context()
            if isinstance(context.get("meta"), type(None)):
                context["meta"] = {}

            # ⭐ 记忆集成：任务完成后保存洞察
            memory_user_id = context.get("meta", {}).get("memory_user_id")
            if MEMORY_ENABLED and memory_user_id and not context.get("meta", {}).get("authorization_requests"):
                try:
                    # 构建任务结果摘要
                    task_result = {
                        "status": "success",
                        "content": result[:500] if result else "",  # 取前500字符
                        "steps": steps
                    }
                    
                    # 保存记忆
                    save_task_memories(
                        user_id=memory_user_id,
                        task_id=task_id,
                        result=task_result,
                        context={
                            "preferred_language": payload.get("language"),
                            "task_type": task_type,
                            "intent": context.get("meta", {}).get("intent", "unknown"),
                            "user_request": context.get("meta", {}).get("user_request"),
                        },
                        workspace_path=context.get("meta", {}).get("workspace_path"),
                    )
                except Exception as e:
                    print(f"\n⚠️ [MEMORY] 保存任务记忆失败: {e}")

            # ── P3 短期记忆写回：conversation_id 存在时写入 ConversationStore ──
            if _SHORT_TERM_MEMORY_ENABLED and not context.get("meta", {}).get("authorization_requests"):
                _conv_id = context.get("meta", {}).get("conversation_id")
                if _conv_id:
                    try:
                        _outcome = _derive_conversation_outcome(steps)
                        save_conversation_memory(
                            _conv_id,
                            intent=context.get("meta", {}).get("intent", "unknown"),
                            prompt=context.get("meta", {}).get("user_request", ""),
                            outcome=_outcome,
                            conclusion=(
                                result[:300] if isinstance(result, str) else str(result)[:300]
                            ),
                            workspace_path=context.get("meta", {}).get("workspace_path"),
                        )
                        print(f"\n🔄 [Conversation] 短期记忆写回完成: {_conv_id} (outcome={_outcome})")
                    except Exception as e:
                        print(f"\n⚠️ [Conversation] 短期记忆写回失败: {e}")

            # 写回成功结果
            result_key = f"task_result:{task_id}"
            # 规范化 context：剔除内部对象（_tree_result 等），转 JSON 安全类型
            safe_context = TaskModel.normalize_for_serialization(context)
            result_data = TaskModel.create_task_result_success(
                task_id=task_id,
                task_type=task_type,
                result=result,
                worker_id=WORKER_ID,
                started_at=started_at,
                steps=steps,
                events=events,
                context=safe_context,
            )
            if task.get("protocol_version") == PROTOCOL_VERSION:
                result_data["protocol_version"] = task["protocol_version"]
                result_data["trace_id"] = task["trace_id"]

            # G2.2 Inject 2: 注入 task_state 并验证转换合法性
            # ⭐ Phase E: 任务级证据校验（提交前最后一道门）
            # 必须在 COMPLETED 或 WAITING_AUTHORIZATION 之前执行，
            # 确保证据缺失时直接走外层 FAILED 路径，不发布成功事件
            _exec_chain = context.get("meta", {}).get("execution_chain", [])
            if "workspace" in _exec_chain:
                _meta = context.get("meta", {})
                # G8.10-R2: 空工作区/未扫描 = 架构设计/文档任务，跳过任务级证据门
                _ws_scan = _meta.get("workspace_scan")
                _is_empty = (
                    _ws_scan is None
                    or (isinstance(_ws_scan, dict) and _ws_scan.get("python_file_count", -1) == 0)
                )
                if _is_empty:
                    pass  # 设计任务，无需工作区证据
                else:
                    gate = validate_workspace_evidence(_meta)
                    if not gate.can_proceed():
                        raise EvidenceGateBlocked(
                            f"任务级校验：执行链包含 workspace 步骤但证据状态为 {gate.status}"
                        )
                    result_data["evidence_gate"] = gate.to_dict()
                    _ws_evidence = _meta.get("workspace_evidence", {})
                    _evidence_hits = _meta.get("evidence_search_hits", [])
                    print(
                        f"\n✅ [EvidenceGate] 任务 {task_id} 证据准入通过 "
                        f"({len(_ws_evidence)} 个文件, {len(_evidence_hits)} 次命中)"
                    )

            # G5.1: 架构证据 Gate（仅 architecture intent，无条件执行）
            _intent = (context.get("meta") or {}).get("intent", "")
            if _intent == "architecture":
                arch_gate = validate_architecture_evidence(context.get("meta") or {})
                if not arch_gate.can_proceed():
                    raise EvidenceGateBlocked(
                        f"任务级校验：架构意图但架构证据状态为 {arch_gate.status}，"
                        f"原因: {arch_gate.failure_reason}"
                    )
                result_data["architecture_evidence_gate"] = arch_gate.to_dict()
                print(
                    f"\n✅ [ArchEvidenceGate] 任务 {task_id} 架构证据准入通过 "
                    f"(module_count={((context.get('meta') or {}).get('architecture_evidence') or {}).get('module_count', 0)})"
                )

            has_authorization = bool((context.get("meta") or {}).get("authorization_requests"))
            if has_authorization:
                if not transition_is_legal(current_task_state, TASK_STATE_WAITING_AUTHORIZATION):
                    raise ContractViolationError(
                        f"非法 task state 转换: {current_task_state} → {TASK_STATE_WAITING_AUTHORIZATION}"
                    )
                result_data["task_state"] = TASK_STATE_WAITING_AUTHORIZATION
                events.append({
                    "event": AUDIT_EVENT_TASK_AWAITING_AUTHORIZATION,
                    "task_id": task_id,
                    "sequence": len(events) + 1,
                    "timestamp": int(time.time() * 1000),
                    "idempotency_key": f"{task_id}:{AUDIT_EVENT_TASK_AWAITING_AUTHORIZATION}:{len(events)}",
                })
            else:
                if not transition_is_legal(current_task_state, TASK_STATE_COMPLETED):
                    raise ContractViolationError(
                        f"非法 task state 转换: {current_task_state} → {TASK_STATE_COMPLETED}"
                    )
                result_data["task_state"] = TASK_STATE_COMPLETED
                events.append({
                    "event": AUDIT_EVENT_TASK_COMPLETED,
                    "task_id": task_id,
                    "sequence": len(events) + 1,
                    "timestamp": int(time.time() * 1000),
                    "idempotency_key": f"{task_id}:{AUDIT_EVENT_TASK_COMPLETED}:{len(events)}",
                })

            # G2.2: 契约验证——硬违规阻断，兼容性警告放行
            violations = validate_result_contract(result_data)
            if violations:
                hard_violation_fields = {"task_state|status", "task_state", "status"}
                hard_violations = [v for v in violations if v.field in hard_violation_fields]
                if hard_violations:
                    print(f"\n⛔ [CONTRACT] 任务 {task_id} 存在硬性契约违规 ({len(hard_violations)} 项):")
                    for v in hard_violations:
                        print(f"   ⛔ {v.field}: {v.message}")
                    raise ContractViolationError(
                        f"任务 {task_id} 的结果违反状态契约，拒绝发布"
                    )
                print(f"\n⚠️ [CONTRACT WARNING] 任务 {task_id} ({len(violations)} 项):")
                for v in violations:
                    print(f"   ⚠️ {v.field}: {v.message}")

            redis.set(result_key, json.dumps(
                TaskModel.normalize_for_serialization(result_data)
            ))

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
                    timeout=30,
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
                # 规范化 context（错误路径同样需要安全序列化）
                safe_error_context = TaskModel.normalize_for_serialization(context)
                error_result = TaskModel.create_task_result_error(
                    task_id=task_id,
                    task_type=task_type,
                    error_message=str(e),
                    worker_id=WORKER_ID,
                    error_code=(
                        ERROR_CODE_CONTRACT_VIOLATION
                        if isinstance(e, ContractViolationError)
                        else ERROR_CODE_EVIDENCE_GATE_BLOCKED
                        if isinstance(e, EvidenceGateBlocked)
                        else ERROR_CODE_TASK_PROTOCOL_ERROR
                        if isinstance(e, TaskProtocolError)
                        else ERROR_CODE_MODEL_CALL_ERROR
                    ),
                    error_stack=traceback.format_exc(),
                    started_at=started_at,
                    retry_count=retry_count,
                    steps=steps,
                    events=events,
                    context=safe_error_context,
                )

                print("\n" + "=" * 60)
                print("任务失败，错误结果已写入 Redis:")
                print(TaskModel.pretty_print(error_result))
                print("=" * 60 + "\n")

            # G2.2 Inject 3/4: 失败路径 → task_state → FAILED
            if not transition_is_legal(current_task_state, TASK_STATE_FAILED):
                raise ContractViolationError(
                    f"非法 task state 转换: {current_task_state} → {TASK_STATE_FAILED}"
                )
            error_result["task_state"] = TASK_STATE_FAILED
            events.append({
                "event": AUDIT_EVENT_TASK_FAILED,
                "task_id": task_id,
                "sequence": len(events) + 1,
                "timestamp": int(time.time() * 1000),
                "idempotency_key": f"{task_id}:{AUDIT_EVENT_TASK_FAILED}:{len(events)}",
            })

            # G2.2: 契约验证（不做阻隔）
            violations = validate_result_contract(error_result)
            if violations:
                print(f"\n⚠️ [CONTRACT] 任务 {task_id} 违反契约 ({len(violations)} 项):")
                for v in violations:
                    print(f"   - {v.field}: {v.message}")

            if (
                task.get("protocol_version") == PROTOCOL_VERSION
                and isinstance(task.get("trace_id"), str)
                and task["trace_id"].strip()
            ):
                error_result["protocol_version"] = PROTOCOL_VERSION
                error_result["trace_id"] = task["trace_id"]

            if result_key:
                redis.set(result_key, json.dumps(
                    TaskModel.normalize_for_serialization(error_result)
                ))

            try:
                notify_url = f"{NODE_API_URL}/task/notify/{task_id}"
                print(f"\n📡 正在通知 Node.js (错误任务): {notify_url}")

                response = requests.post(
                    notify_url,
                    json=error_result,
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )

                if response.status_code == 200:
                    print("✅ Node.js 已成功接收错误通知，将推送给前端")
                else:
                    print(f"⚠️ Node.js 返回错误状态码: {response.status_code}")
            except Exception as notify_error:
                print(f"⚠️ 通知 Node.js 失败: {notify_error}")

            if task_id:
                clear_stop_flag(task_id)

            if not is_cancelled and task_id:
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