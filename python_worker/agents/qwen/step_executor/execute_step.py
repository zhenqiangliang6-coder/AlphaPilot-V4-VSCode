# -*- coding: utf-8 -*-
# step_executor/execute_step.py
# ---------------------------------------------------------
# Qwen Worker v3.0 — 统一步骤调度器（Step Dispatcher）
# - 根据 step["type"] 调用对应的 run_xxx_step
# - 自动支持 v3.0 新步骤（docstring）
# - 自动传递 task_id（流式输出）
# - 工业级容错
# ---------------------------------------------------------

from .analyze_step import run_analyze_step
from .plan_step import run_plan_step
from .write_step import run_write_step
from .refine_step import run_refine_step

from .test_step import run_test_step
from .fix_step import run_fix_step
from .profile_step import run_profile_step
from .doc_step import run_doc_step
from .docstring_step import run_docstring_step   # ⭐ v3.0 docstring 步骤
from .respond_step import run_respond_step
from .workspace_step import run_workspace_step

# ⭐ v4.3 vision_analysis — 一等公民视觉分析步骤
from ...vision_step import run_vision_step


# ---------------------------------------------------------
# 步骤类型 → 执行函数 的映射表（v4.3 全量）
# ---------------------------------------------------------
STEP_DISPATCHER = {
    # ⭐ v4.3 vision 一等公民步骤
    "vision_analysis": run_vision_step,

    "analyze": run_analyze_step,
    "plan": run_plan_step,
    "write": run_write_step,
    "refine": run_refine_step,

    "test": run_test_step,
    "fix": run_fix_step,
    "profile": run_profile_step,
    "doc": run_doc_step,

    # ⭐ v3.0 新增步骤
    "docstring": run_docstring_step,
    "respond": run_respond_step,
    "workspace": run_workspace_step,
}


def _is_task_terminated(context: dict) -> bool:
    """P2-6: 检查任务是否已进入终止状态 (COMPLETED/FAILED)。"""
    if context.get("_task_terminated"):
        print(f"[StateGuard] 跳过 step_finished — 任务已终止")
        return True
    # G2.2 兼容: 直接检查 task_state 字段
    ts = context.get("_task_state", "")
    if ts in ("COMPLETED", "FAILED"):
        print(f"[StateGuard] 跳过 step_finished — task_state={ts}")
        return True
    return False


def execute_step(task_id: str, step: dict, events: list, context: dict):
    """
    v3.0 统一步骤执行入口：
    - Worker 调用本函数，而不是直接调用 run_xxx_step
    - 根据 step["type"] 自动路由到对应的执行器
    - 自动传递 task_id（用于流式输出）
    """

    step_type = step.get("type")

    if step_type not in STEP_DISPATCHER:
        step["output"] = {"text": f"未知步骤类型：{step_type}"}
        return

    handler = STEP_DISPATCHER[step_type]

    # ⭐ 自动检测 handler 是否支持 task_id 参数
    import inspect
    sig = inspect.signature(handler)

    # ⭐ Phase F: 输出准入 — 证据门
    # 仅对可能输出项目事实的步骤类型执行准入检查
    EVIDENCE_GATED_STEPS = {"analyze", "plan", "respond", "doc", "docstring"}
    if step_type in EVIDENCE_GATED_STEPS:
        meta = context.get("meta", {})
        if "workspace" in meta.get("execution_chain", []):
            from ....task_state_contract import validate_workspace_evidence, EvidenceGateBlocked
            from ....worker_config import stream_chunk as _sc
            gate = validate_workspace_evidence(meta)
            if not gate.can_proceed():
                if task_id:
                    _sc(task_id, "工作区证据不可用，分析终止", phase=step_type, channel="status")
                raise EvidenceGateBlocked(
                    f"步骤 '{step_type}' 需要工作区证据，但证据状态为 {gate.status}"
                )

    # P0：步骤开始事件 → 前端显示阶段指示器和思考动画
    if task_id:
        try:
            from ....worker_config import step_started as _emit_step_started
            _emit_step_started(task_id, step.get("id", step_type), step_type)
        except Exception as _e:
            print(f"⚠️ step_started emit 失败：{_e}")

    try:
        if "task_id" in sig.parameters:
            # 支持流式输出的新签名
            handler(step, context, events, task_id=task_id)
        else:
            # 向后兼容旧签名
            handler(step, context, events)

    except Exception as e:
        step["output"] = {"text": f"步骤执行失败：{e}"}
        raise e

    finally:
        # P0：步骤完成事件 → 前端更新 StepTree 为 completed
        if task_id:
            try:
                from ....worker_config import step_finished as _emit_step_finished
                _emit_step_finished(task_id, step.get("id", step_type), step_type)
            except Exception as _e:
                print(f"⚠️ step_finished emit 失败：{_e}")

    # ⭐ P2-6: 终止状态守卫检查
    #    若任务已被标记为终止（context["_task_terminated"]），
    #    不再追加 step_finished，防止 COMPLETED/FAILED 后仍发事件
    if not _is_task_terminated(context):
        events.append({
            "event": "step_finished",
            "task_id": task_id,
            "step_id": step.get("id"),
            "step_type": step_type,
            "output": step.get("output", {})
        })
    else:
        step.setdefault("_guard_skipped", True)