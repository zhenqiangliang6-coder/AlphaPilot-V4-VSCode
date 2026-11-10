# -*- coding: utf-8 -*-
# compound_executor.py
# ---------------------------------------------------------
# G8.0: 复合任务多阶段执行
#
# Responsibility:
#   - 在执行链主阶段（Phase 1）完成后执行后续阶段
#   - 支持的后续阶段: execute_operation / write_code / refactor / fix_code / code_review
#
# Extracted from qwen_worker_v2.py
# ---------------------------------------------------------

from ...task_state_contract import (
    STEP_STATE_PENDING,
    STEP_STATE_RUNNING,
    STEP_STATE_COMPLETED,
    STEP_STATE_FAILED,
)
from ...worker_config import stream_chunk

from .execution_chain import build_execution_chain, create_steps_from_chain
from .step_runner import run_execution_loop


# ── 后续阶段代码生成类意图 → 执行链映射 ──────────────────────
_CODE_PHASE_CHAINS = {
    "write_code": "write_code",
    "refactor": "refactor",
    "fix_code": "fix_code",
    "code_review": "code_review",
    "workspace_maintenance": "workspace_maintenance",
}


def exec_compound_phases(
    compound_plan,
    execution_plan: dict,
    task_id: str,
    events: list,
    context: dict,
):
    """在主链（Phase 1）完成后，执行后续阶段。

    支持的后续阶段类型:
      - execute_operation → operate_step (git / shell / env)
      - write_code / refactor / fix_code / code_review → 完整执行链

    设计原则：
    - 不复制 execute_task 的重型设置（memory, workspace scan 等）
    - 每个后续阶段是轻量级 step 执行
    - 结果写入 context，供返回给用户
    """
    if not compound_plan or not compound_plan.is_compound:
        return

    for phase_idx, phase in enumerate(compound_plan.phases[1:], start=2):
        if _execution_is_blocked(context):
            print(
                f"   ⏸️ [G8.0] Phase {phase_idx} 未执行："
                f"前置步骤状态为 {context.get('meta', {}).get('execution_state')}"
            )
            break

        phase_tag = f"phase_{phase_idx}"

        if phase.type == "execute_operation":
            completed = _exec_operation_phase(
                phase, phase_idx, phase_tag, task_id, events, context
            )

        elif phase.type in _CODE_PHASE_CHAINS:
            completed = _exec_code_phase(
                phase,
                phase_idx,
                phase_tag,
                execution_plan,
                task_id,
                events,
                context,
            )

        else:
            print(f"   ⚠️ [G8.0] Phase {phase_idx}: 不支持的类型 [{phase.type}]，跳过")
            continue

        if not completed:
            break


def _exec_operation_phase(phase, phase_idx: int, phase_tag: str,
                           task_id: str, events: list, context: dict) -> bool:
    print(f"\n🚀 [G8.0] Phase {phase_idx}: execute_operation — {phase.prompt[:60]}")

    _stream_instruction_chunk(task_id, phase_idx, phase.prompt, phase_tag)

    op_step = {
        "type": "operate",
        "status": STEP_STATE_PENDING,
        "output": {},
        "input": {"prompt": phase.prompt.strip()},
    }

    try:
        from .step_executor.operate_step import run_operate_step
        op_step["status"] = STEP_STATE_RUNNING
        run_operate_step(op_step, context, events)
        op_step["status"] = STEP_STATE_COMPLETED

        result_text = op_step.get("output", {}).get("text", "")
        _stream_answer_chunk(task_id, phase_idx, phase_tag, result_text)
        print(f"   ✅ [G8.0] Phase {phase_idx} (execute_operation) 完成")
        return True
    except Exception as e:
        op_step["status"] = STEP_STATE_FAILED
        op_step["output"] = {"text": f"Phase {phase_idx} 执行失败: {e}"}
        print(f"   ❌ [G8.0] Phase {phase_idx} 失败: {e}")
        _stream_error_chunk(task_id, phase_idx, phase_tag, e)
        return False


def _exec_code_phase(phase, phase_idx: int, phase_tag: str,
                      execution_plan: dict,
                      task_id: str, events: list, context: dict) -> bool:
    intent_label = _CODE_PHASE_CHAINS[phase.type]
    print(f"\n🚀 [G8.0] Phase {phase_idx}: {phase.type} — {phase.prompt[:60]}")

    _stream_instruction_chunk(task_id, phase_idx, phase.prompt, phase_tag)

    try:
        chain = build_execution_chain(intent_label, phase.prompt)
        phase_steps = create_steps_from_chain(
            chain, phase.prompt.strip(), "engineer", intent_label
        )
        if not phase_steps:
            print(f"   ⚠️ [G8.0] Phase {phase_idx}: 无可用步骤，跳过")
            return False

        run_execution_loop(
            phase_steps,
            execution_plan,
            task_id,
            events,
            context,
            intent_label,
            context.get("meta", {}).get("collaboration_mode", "engineer"),
        )

        result_text = "\n".join(
            s.get("output", {}).get("text", "")
            for s in phase_steps if s.get("output", {}).get("text")
        )
        _stream_answer_chunk(task_id, phase_idx, phase_tag, result_text)
        blocked = _execution_is_blocked(context) or any(
            step.get("status") == STEP_STATE_FAILED for step in phase_steps
        )
        if blocked:
            print(f"   ⛔ [G8.0] Phase {phase_idx} 未通过执行/授权门控")
            return False
        print(f"   ✅ [G8.0] Phase {phase_idx} ({phase.type}) 完成")
        return True
    except Exception as e:
        print(f"   ❌ [G8.0] Phase {phase_idx} ({phase.type}) 失败: {e}")
        _stream_error_chunk(task_id, phase_idx, phase_tag, e)
        return False


def _execution_is_blocked(context: dict) -> bool:
    meta = context.get("meta", {})
    if meta.get("execution_state") in {"awaiting_authorization", "validation_failed"}:
        return True
    return any(
        request.get("status") in {"awaiting_host_policy", "awaiting_user_confirmation"}
        for request in meta.get("authorization_requests", [])
        if isinstance(request, dict)
    )


# ── stream helpers ───────────────────────────────────────────


def _stream_instruction_chunk(task_id, phase_idx: int, prompt: str, phase_tag: str):
    if not task_id:
        return
    try:
        stream_chunk(
            task_id,
            f"\n\n---\n📦 **Phase {phase_idx}: {prompt.strip()}**\n\n",
            phase=phase_tag,
            channel="instruction",
        )
    except Exception as error:
        print(f"   ⚠️ [G8.0] Phase {phase_idx} 指令流发送失败: {error}")


def _stream_answer_chunk(task_id, phase_idx: int, phase_tag: str, result_text: str):
    if not task_id or not result_text:
        return
    try:
        stream_chunk(
            task_id,
            f"✅ Phase {phase_idx} 完成\n{result_text[:2000]}",
            phase=phase_tag,
            channel="answer",
        )
    except Exception as error:
        print(f"   ⚠️ [G8.0] Phase {phase_idx} 结果流发送失败: {error}")


def _stream_error_chunk(task_id, phase_idx: int, phase_tag: str, error):
    if not task_id:
        return
    try:
        stream_chunk(
            task_id,
            f"❌ Phase {phase_idx} 执行异常: {error}",
            phase=phase_tag,
            channel="error",
        )
    except Exception as stream_error:
        print(f"   ⚠️ [G8.0] Phase {phase_idx} 错误流发送失败: {stream_error}")