# -*- coding: utf-8 -*-
# step_executor/execute_step.py
# ---------------------------------------------------------
# Local LLM Worker v3.0 — 统一步骤调度器（Step Dispatcher）
# - 根据 step["type"] 调用对应的 run_xxx_step
# - ⭐ v3.0：自动检测并传递 task_id（支持流式输出）
# - ⭐ v3.0：通过 context['_custom_api_func'] 注入自定义 API 函数
# - 工业级容错 + 与 Qwen Worker v2 完全对齐
# ---------------------------------------------------------

from .analyze_step import run_analyze_step
from .plan_step import run_plan_step
from .write_step import run_write_step
from .refine_step import run_refine_step

from .test_step import run_test_step
from .fix_step import run_fix_step
from .profile_step import run_profile_step
from .doc_step import run_doc_step
from .docstring_step import run_docstring_step


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

    # ⭐ v3.0 新增步骤
    "docstring": run_docstring_step,
}


def execute_step(task_id: str, step: dict, events: list, context: dict):
    """
    v3.0 统一步骤执行入口（与 Qwen Worker v2 完全对齐）：
    - Worker 调用本函数，而不是直接调用 run_xxx_step
    - 根据 step["type"] 自动路由到对应的执行器
    - ⭐ 自动检测 handler 是否支持 task_id 参数（使用 inspect）
    - ⭐ 通过 context['_custom_api_func'] 注入自定义 API 函数
    
    参数:
        task_id: 任务 ID（用于流式输出）
        step: 步骤定义字典
        events: 事件列表
        context: 上下文对象（可包含 _custom_api_func）
    """

    step_type = step.get("type")

    if step_type not in STEP_DISPATCHER:
        step["output"] = {"text": f"未知步骤类型：{step_type}"}
        return

    handler = STEP_DISPATCHER[step_type]

    # ⭐ 自动检测 handler 是否支持 task_id 参数（与 Qwen Worker v2 一致）
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
