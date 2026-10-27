# -*- coding: utf-8 -*-
# test_qwen_contract_paths.py
# ---------------------------------------------------------
# G2.2: Qwen Worker 契约路径测试（测试先行，red → green）
#
# 目的：在 Inject 1-4 实施前，先定义 result_data 必须通过的契约验证场景。
#       这些测试使用 validate_result_contract() 验证模拟的 Qwen Worker 输出，
#       确保 Worker 在增加 task_state 和审计事件后，输出符合契约。
# ---------------------------------------------------------

import time
import pytest
from task_state_contract import (
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
    AUDIT_EVENT_TASK_STARTED,
    AUDIT_EVENT_TASK_COMPLETED,
    AUDIT_EVENT_TASK_FAILED,
    AUDIT_EVENT_TASK_AWAITING_AUTHORIZATION,
    AUDIT_EVENT_STEP_STARTED,
    AUDIT_EVENT_STEP_COMPLETED,
    AUDIT_EVENT_STEP_FAILED,
    AUDIT_EVENT_STEP_SKIPPED,
    ERROR_CODE_TASK_PROTOCOL_ERROR,
    validate_result_contract,
)


def _mk_ts():
    return int(time.time() * 1000)


def make_qwen_result(
    task_id="task-q-001",
    task_type="qwen-coder-7b",
    task_state=TASK_STATE_COMPLETED,
    legacy_status="done",
    steps=None,
    events=None,
    error=None,
    protocol_version="1.0",
    trace_id=None,
):
    """构造与 Qwen Worker 实际 result_data 结构一致的字典。"""
    now = _mk_ts()
    result = {
        "version": "2.0",
        "task_id": task_id,
        "type": task_type,
        "status": legacy_status,
        "task_state": task_state,
        "result": "=== 任务输出文本 ===",
        "error": error,
        "steps": steps or [],
        "events": events or [],
        "context": {},
        "meta": {
            "started_at": now - 5000,
            "finished_at": now,
            "worker_id": "qwen-worker-test",
            "duration_ms": 5000,
        },
    }
    if protocol_version:
        result["protocol_version"] = protocol_version
    if trace_id:
        result["trace_id"] = trace_id
    return result


def make_step(step_type, step_status, step_id=None, reason=None):
    step = {
        "id": step_id or f"step-{step_type}-1",
        "type": step_type,
        "status": step_status,
        "input": {"prompt": f"执行 {step_type}"},
        "output": {"text": f"{step_type} 输出"},
    }
    if reason:
        step["reason"] = reason
    return step


def make_task_event(event_type, task_id, sequence):
    return {
        "event": event_type,
        "task_id": task_id,
        "sequence": sequence,
        "timestamp": _mk_ts(),
        "idempotency_key": f"{task_id}:{event_type}:{sequence}",
    }


def make_step_event(event_type, task_id, step_id, sequence):
    return {
        "event": event_type,
        "task_id": task_id,
        "step_id": step_id,
        "sequence": sequence,
        "timestamp": _mk_ts(),
        "idempotency_key": f"{task_id}:step:{step_id}:{event_type}:{sequence}",
    }


# ===== T7: Qwen 正常完成（所有步骤 completed，task_state=COMPLETED）=====

def test_t7_qwen_normal_completion_passes_contract():
    steps = [
        make_step("analyze", STEP_STATE_COMPLETED, "step-analyze-1"),
        make_step("write", STEP_STATE_COMPLETED, "step-write-1"),
        make_step("test", STEP_STATE_COMPLETED, "step-test-1"),
    ]
    seq = 0
    def s():
        nonlocal seq; seq += 1; return seq
    events = [
        make_task_event(AUDIT_EVENT_TASK_STARTED, "task-q-001", s()),
        make_step_event(AUDIT_EVENT_STEP_STARTED, "task-q-001", "step-analyze-1", s()),
        make_step_event(AUDIT_EVENT_STEP_COMPLETED, "task-q-001", "step-analyze-1", s()),
        make_step_event(AUDIT_EVENT_STEP_STARTED, "task-q-001", "step-write-1", s()),
        make_step_event(AUDIT_EVENT_STEP_COMPLETED, "task-q-001", "step-write-1", s()),
        make_step_event(AUDIT_EVENT_STEP_STARTED, "task-q-001", "step-test-1", s()),
        make_step_event(AUDIT_EVENT_STEP_COMPLETED, "task-q-001", "step-test-1", s()),
        make_task_event(AUDIT_EVENT_TASK_COMPLETED, "task-q-001", s()),
    ]
    result = make_qwen_result(steps=steps, events=events)
    v = validate_result_contract(result)
    assert v == [], f"T7 正常完成不应有违规: {[x.message for x in v]}"


# ===== T8: 协议错误（PENDING → FAILED，无 RUNNING，零步骤）=====

def test_t8_qwen_protocol_error_skip_running():
    result = make_qwen_result(
        task_id="task-q-protocol-1",
        task_state=TASK_STATE_FAILED,
        legacy_status="error",
        error={
            "message": "任务协议校验失败: 缺少必要字段",
            "code": ERROR_CODE_TASK_PROTOCOL_ERROR,
            "stack": None,
            "retryable": False,
        },
        steps=[],
        events=[
            make_task_event(AUDIT_EVENT_TASK_FAILED, "task-q-protocol-1", 1),
        ],
    )
    v = validate_result_contract(result)
    assert v == [], f"T8 协议错误路径不应有违规: {[x.message for x in v]}"


# ===== T9: 步骤执行失败（completed + failed 混合）=====

def test_t9_qwen_step_execution_failure():
    steps = [
        make_step("analyze", STEP_STATE_COMPLETED, "step-analyze-1"),
        make_step("write", STEP_STATE_COMPLETED, "step-write-1"),
        make_step("test", STEP_STATE_FAILED, "step-test-1"),
    ]
    seq = 0
    def s():
        nonlocal seq; seq += 1; return seq
    events = [
        make_task_event(AUDIT_EVENT_TASK_STARTED, "task-q-001", s()),
        make_step_event(AUDIT_EVENT_STEP_STARTED, "task-q-001", "step-analyze-1", s()),
        make_step_event(AUDIT_EVENT_STEP_COMPLETED, "task-q-001", "step-analyze-1", s()),
        make_step_event(AUDIT_EVENT_STEP_STARTED, "task-q-001", "step-write-1", s()),
        make_step_event(AUDIT_EVENT_STEP_COMPLETED, "task-q-001", "step-write-1", s()),
        make_step_event(AUDIT_EVENT_STEP_STARTED, "task-q-001", "step-test-1", s()),
        make_step_event(AUDIT_EVENT_STEP_FAILED, "task-q-001", "step-test-1", s()),
        make_task_event(AUDIT_EVENT_TASK_FAILED, "task-q-001", s()),
    ]
    result = make_qwen_result(
        task_state=TASK_STATE_FAILED,
        legacy_status="error",
        error={"message": "test failed", "code": "STEP_ERROR", "retryable": True},
        steps=steps,
        events=events,
    )
    v = validate_result_contract(result)
    assert v == [], f"T9 步骤失败不应有违规: {[x.message for x in v]}"


# ===== T10: 等待授权（WAITING_AUTHORIZATION + 1 awaiting 步骤）=====

def test_t10_qwen_awaiting_authorization():
    steps = [
        make_step("analyze", STEP_STATE_COMPLETED, "step-analyze-1"),
        make_step("write", STEP_STATE_COMPLETED, "step-write-1"),
        make_step("test", STEP_STATE_AWAITING_AUTHORIZATION, "step-test-1"),
    ]
    seq = 0
    def s():
        nonlocal seq; seq += 1; return seq
    events = [
        make_task_event(AUDIT_EVENT_TASK_STARTED, "task-q-001", s()),
        make_step_event(AUDIT_EVENT_STEP_STARTED, "task-q-001", "step-analyze-1", s()),
        make_step_event(AUDIT_EVENT_STEP_COMPLETED, "task-q-001", "step-analyze-1", s()),
        make_step_event(AUDIT_EVENT_STEP_COMPLETED, "task-q-001", "step-write-1", s()),
        make_task_event(AUDIT_EVENT_TASK_AWAITING_AUTHORIZATION, "task-q-001", s()),
    ]
    result = make_qwen_result(
        task_state=TASK_STATE_WAITING_AUTHORIZATION,
        legacy_status="awaiting_authorization",
        steps=steps,
        events=events,
    )
    v = validate_result_contract(result)
    assert v == [], f"T10 等待授权不应有违规: {[x.message for x in v]}"


# ===== T11: 缺失 task_state 且缺失 status → 双重缺失违规 =====

def test_t11_qwen_both_fields_missing_is_violation():
    result = make_qwen_result()
    del result["task_state"]
    del result["status"]
    v = validate_result_contract(result)
    violation_fields = [x.field for x in v]
    assert "task_state|status" in violation_fields, (
        f"T11 两个字段均缺失应被检测，违规字段: {violation_fields}"
    )


# ===== T12: task_state=FAILED 但步骤有 running → 终态不能含 running ====

def test_t12_qwen_terminal_with_running_step():
    steps = [
        make_step("analyze", STEP_STATE_COMPLETED, "step-1"),
        make_step("write", STEP_STATE_RUNNING, "step-2"),
    ]
    result = make_qwen_result(
        task_state=TASK_STATE_FAILED,
        legacy_status="error",
        steps=steps,
    )
    v = validate_result_contract(result)
    violation_msgs = [x.message for x in v]
    assert any("终态" in m and "running" in m for m in violation_msgs), (
        f"T12 FAILED 状态含 running 步骤应被检测，违规: {violation_msgs}"
    )


# ===== T13: skipped 步骤缺少 reason → 违规 =====

def test_t13_qwen_skipped_without_reason():
    steps = [
        make_step("analyze", STEP_STATE_COMPLETED, "step-1"),
        make_step("fix", STEP_STATE_SKIPPED, "step-2"),
        make_step("test", STEP_STATE_COMPLETED, "step-3"),
    ]
    result = make_qwen_result(steps=steps)
    v = validate_result_contract(result)
    violation_fields = [x.field for x in v]
    # reason 缺失在 steps[1].reason
    assert any("steps[1]" in f and "reason" in f for f in violation_fields), (
        f"T13 skipped 无 reason 应被检测，违规字段: {violation_fields}"
    )


# ===== T14: 用户取消（中途取消 → task_failed）=====

def test_t14_qwen_user_cancellation():
    steps = [
        make_step("analyze", STEP_STATE_COMPLETED, "step-analyze-1"),
        make_step("write", STEP_STATE_FAILED, "step-write-1"),
    ]
    steps[1]["output"] = {"text": "任务已被用户取消"}
    seq = 0
    def s():
        nonlocal seq; seq += 1; return seq
    events = [
        make_task_event(AUDIT_EVENT_TASK_STARTED, "task-q-001", s()),
        make_step_event(AUDIT_EVENT_STEP_STARTED, "task-q-001", "step-analyze-1", s()),
        make_step_event(AUDIT_EVENT_STEP_COMPLETED, "task-q-001", "step-analyze-1", s()),
        make_step_event(AUDIT_EVENT_STEP_STARTED, "task-q-001", "step-write-1", s()),
        make_step_event(AUDIT_EVENT_STEP_FAILED, "task-q-001", "step-write-1", s()),
        make_task_event(AUDIT_EVENT_TASK_FAILED, "task-q-001", s()),
    ]
    result = make_qwen_result(
        task_state=TASK_STATE_FAILED,
        legacy_status="error",
        error={"message": "任务已被用户取消", "code": "CANCELLED", "retryable": False},
        steps=steps,
        events=events,
    )
    v = validate_result_contract(result)
    assert v == [], f"T14 取消路径不应有违规: {[x.message for x in v]}"


# ===== T15: task_state 与 legacy status 不一致 → 违规 =====

def test_t15_qwen_state_status_mismatch():
    result = make_qwen_result(
        task_state=TASK_STATE_COMPLETED,
        legacy_status="error",
        steps=[make_step("analyze", STEP_STATE_COMPLETED, "step-1")],
    )
    v = validate_result_contract(result)
    assert len(v) > 0, "T15 COMPLETED + status=error 应被检测为不一致"


# ===== T16: 无事件记录但完成路径仍然合法 =====

def test_t16_qwen_no_events_still_valid():
    steps = [
        make_step("analyze", STEP_STATE_COMPLETED, "step-1"),
        make_step("write", STEP_STATE_COMPLETED, "step-2"),
    ]
    result = make_qwen_result(steps=steps, events=[])
    v = validate_result_contract(result)
    assert v == [], f"T16 无事件不应导致违规: {[x.message for x in v]}"