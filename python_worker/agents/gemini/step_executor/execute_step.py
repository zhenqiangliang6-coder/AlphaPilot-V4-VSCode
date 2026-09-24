# -*- coding: utf-8 -*-
# step_executor/execute_step.py
# ---------------------------------------------------------
# Gemini Worker v3.0 — 统一步骤调度器（Step Dispatcher）
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


# ---------------------------------------------------------
# 步骤类型 → 执行函数 的映射表（v3.0 全量）
# ---------------------------------------------------------
STEP_DISPATCHER = {
    "analyze": run_analyze_step,
    "plan": run_plan_step,
    "write": run_write_step,
    "refine": run_refine_step,

    "test": run_test_step,
    "fix": run_fix_step,
    "profile": run_profile_step,
    "doc": run_doc_step,
}


# ⭐ 非核心步骤列表（异常时降级而非中断）
NON_CRITICAL_STEPS = {"doc", "profile", "docstring"}


def execute_step(task_id: str, step: dict, events: list, context: dict):
    """
    v3.0 统一步骤执行入口：
    - Worker 调用本函数，而不是直接调用 run_xxx_step
    - 根据 step["type"] 自动路由到对应的执行器
    - 自动传递 task_id（用于流式输出）
    - ⭐ 非核心步骤异常时降级处理
    """

    step_type = step.get("type")

    if step_type not in STEP_DISPATCHER:
        step["output"] = {"text": f"未知步骤类型：{step_type}"}
        return

    handler = STEP_DISPATCHER[step_type]

    # ⭐ 自动检测 handler 是否支持 task_id 参数
    import inspect
    sig = inspect.signature(handler)

    try:
        if "task_id" in sig.parameters:
            # 支持流式输出的新签名
            handler(step, context, events, task_id=task_id)
        else:
            # 向后兼容旧签名
            handler(step, context, events)

    except Exception as e:
        # ⭐ 非核心步骤异常降级处理
        if step_type in NON_CRITICAL_STEPS:
            print(f"⚠️ [Gemini Worker] 非核心步骤 '{step_type}' 执行失败，降级处理: {e}")
            step["status"] = "warning"
            step["output"] = {"text": f"⚠️ {step_type} 步骤执行失败（已降级）: {e}"}
            return
        
        # 核心步骤异常则正常抛出
        step["output"] = {"text": f"步骤执行失败：{e}"}
        raise e

    # ⭐ 记录步骤完成事件（供前端展示）
    events.append({
        "event": "step_finished",
        "task_id": task_id,
        "step_id": step.get("id"),
        "step_type": step_type,
        "output": step.get("output", {})
    })
