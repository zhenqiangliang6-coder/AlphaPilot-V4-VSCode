# -*- coding: utf-8 -*-
# step_executor/execute_step.py
# ---------------------------------------------------------
# 统一步骤调度器（Step Dispatcher）
# - 根据 step["type"] 调用对应的 run_xxx_step
# - Worker 不需要知道每个步骤的细节
# - 新增步骤时只需要在这里注册即可
# - ⭐ v3.0：支持自定义 api_func（用于流式输出）
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
# 步骤类型 → 执行函数 的映射表
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
    "docstring": run_docstring_step,  # ⭐ Local LLM 独有步骤
}


def execute_step(task_id: str, step: dict, events: list, context: dict, api_func=None):
    """
    统一步骤执行入口：
    - Worker 调用本函数，而不是直接调用 run_xxx_step
    - 根据 step["type"] 自动路由到对应的执行器
    - ⭐ v3.0：支持传入自定义 api_func（用于流式输出）
    
    参数:
        task_id: 任务 ID
        step: 步骤定义字典
        events: 事件列表
        context: 上下文对象
        api_func: 可选的自定义 API 调用函数（签名：api_func(prompt) -> str）
    """

    step_type = step.get("type")

    if step_type not in STEP_DISPATCHER:
        step["output"] = {"text": f"未知步骤类型：{step_type}"}
        return

    handler = STEP_DISPATCHER[step_type]

    # ⭐ v3.0：如果提供了自定义 api_func，将其注入到 context 中
    if api_func is not None:
        context["_custom_api_func"] = api_func

    # 执行步骤
    handler(step, context, events)

    # 清理临时注入的 api_func
    if "_custom_api_func" in context:
        del context["_custom_api_func"]

    # 记录步骤完成事件（供 VSCode 扩展展示）
    events.append({
        "event": "step_finished",
        "task_id": task_id,
        "step_id": step.get("id"),
        "step_type": step_type,
        "output": step.get("output", {})
    })
