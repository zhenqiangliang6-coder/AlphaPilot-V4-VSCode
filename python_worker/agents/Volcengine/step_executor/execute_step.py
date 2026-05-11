# -*- coding: utf-8 -*-
# step_executor/execute_step.py — AlphaPilot OS v3.0
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - 所有步骤调度必须在 Worker 内完成
#    - 前端、Node API、VSCode 插件都不能决定执行链
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - 每个步骤必须遵守统一协议（输入 → 输出 → FileOps）
#    - execute_step 是整个执行链的"最高法院"
#
# 本模块负责：
# 1. 根据 step["type"] 调用对应的 run_xxx_step
# 2. 统一调度所有步骤（analyze → plan → write → test → refine → fix → profile → doc → docstring）
# 3. 统一记录事件流（供 VSCode 扩展展示）
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


# ---------------------------------------------------------
# 步骤类型 → 执行函数 的映射表（协议 = 宪法）
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


def execute_step(task_id: str, step: dict, events: list, context: dict, api_func=None):
    """
    v3.0 统一步骤执行入口（官方 + 智能增强版）
    ---------------------------------------------------------
    Worker = 真相：
        - Worker 决定执行链
        - Worker 决定调用哪个 run_xxx_step

    协议 = 宪法：
        - 每个步骤必须输出 step["output"]
        - 每个步骤必须写入 context["intermediate_results"]
        - 每个步骤必须写入事件流 events
    """

    step_type = step.get("type")

    # =========================================================
    # ① 非法步骤类型（协议保护）
    # =========================================================
    if step_type not in STEP_DISPATCHER:
        step["output"] = {"text": f"未知步骤类型：{step_type}"}
        return

    handler = STEP_DISPATCHER[step_type]

    # ⭐ 自动检测 handler 是否支持 task_id 参数
    import inspect
    sig = inspect.signature(handler)

    # =========================================================
    # ② 执行步骤（支持自定义 API + task_id）
    # =========================================================
    try:
        if "task_id" in sig.parameters:
            # 支持流式输出的新签名
            if api_func:
                handler(step, context, events, task_id=task_id, api_func=api_func)
            else:
                handler(step, context, events, task_id=task_id)
        else:
            # 向后兼容旧签名
            if api_func:
                handler(step, context, events, api_func=api_func)
            else:
                handler(step, context, events)

    except Exception as e:
        step["output"] = {"text": f"步骤执行失败：{e}"}
        raise e

    # =========================================================
    # ③ 记录步骤完成事件（供 VSCode 展示）
    # =========================================================
    events.append({
        "event": "step_finished",
        "task_id": task_id,
        "step_id": step.get("id"),
        "step_type": step_type,
        "output": step.get("output", {})
    })
