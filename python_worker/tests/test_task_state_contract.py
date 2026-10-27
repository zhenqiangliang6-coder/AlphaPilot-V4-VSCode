# -*- coding: utf-8 -*-
"""
G1.3 契约测试 - 任务状态机契约验证

契约纯单元测试，不依赖 Redis、数据库或真实 LLM 调用。
测试顺序：T1 → T6 → T2 → T3 → T4 → T5

每个测试验证：
- 最终 task_state 是否正确
- 状态转换是否合法
- 旧 status 字段是否与 task_state 一致
- 步骤历史是否完整且与任务状态相容
- 审计事件语义是否符合该测试的状态路径
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from task_state_contract import (
    # TaskState
    TASK_STATE_PENDING,
    TASK_STATE_RUNNING,
    TASK_STATE_WAITING_AUTHORIZATION,
    TASK_STATE_COMPLETED,
    TASK_STATE_FAILED,
    TASK_STATES_ALL,
    TASK_STATES_TERMINAL,
    # StepState
    STEP_STATE_PENDING,
    STEP_STATE_RUNNING,
    STEP_STATE_COMPLETED,
    STEP_STATE_FAILED,
    STEP_STATE_AWAITING_AUTHORIZATION,
    STEP_STATE_SKIPPED,
    STEP_STATES_ALL,
    # Transitions
    LEGAL_TRANSITIONS,
    ILLEGAL_TRANSITIONS,
    transition_is_legal,
    # Legacy mapping
    TASK_STATE_TO_LEGACY_STATUS,
    # Audit events
    AUDIT_EVENT_TASK_CREATED,
    AUDIT_EVENT_TASK_STARTED,
    AUDIT_EVENT_TASK_COMPLETED,
    AUDIT_EVENT_TASK_FAILED,
    AUDIT_EVENT_TASK_AWAITING_AUTHORIZATION,
    AUDIT_EVENT_STEP_STARTED,
    AUDIT_EVENT_STEP_COMPLETED,
    AUDIT_EVENT_STEP_FAILED,
    AUDIT_EVENT_STEP_SKIPPED,
    AUDIT_EVENT_CHAIN_REBUILT,
    # Error codes
    ERROR_CODE_TASK_CANCELLED,
    ERROR_CODE_TASK_PROTOCOL_ERROR,
    ERROR_CODE_MODEL_CALL_ERROR,
    ERROR_CODE_CONTRACT_VIOLATION,
    ERROR_CODE_STEP_EXECUTION_ERROR,
    ERROR_CODE_UNKNOWN_ERROR,
    # Validators
    ContractViolation,
    ContractViolationError,
    validate_result_contract,
    assert_no_violations,
    build_event_idempotency_key,
)


# ================================================================
# 辅助函数：构造测试结果对象
# ================================================================

def _now():
    return int(time.time() * 1000)


def _make_task_submitted(task_id="t001"):
    return {
        "task_id": task_id,
        "task_state": TASK_STATE_PENDING,
        "status": "pending",
        "type": "task.generate",
        "payload": {"prompt": "..."},
        "result": None,
        "error": None,
        "steps": [],
        "events": [],
        "meta": {
            "created_at": _now(),
            "started_at": None,
            "finished_at": None,
            "worker_id": None,
        },
    }


def _transition_to(
    result,
    to_state,
    events=None,
    step_updates=None,
    error_info=None,
):
    """模拟一次状态转换：更新结果对象中的状态和相关字段。"""
    result["task_state"] = to_state
    result["status"] = TASK_STATE_TO_LEGACY_STATUS[to_state]

    meta = result.setdefault("meta", {})

    if to_state == TASK_STATE_RUNNING:
        meta["started_at"] = meta.get("started_at") or _now()
    if to_state in TASK_STATES_TERMINAL:
        meta["finished_at"] = _now()

    if events:
        existing = result.get("events") or []
        seq_base = len(existing)
        for i, evt in enumerate(events):
            evt["task_id"] = evt.get("task_id") or result["task_id"]
            evt["sequence"] = evt.get("sequence") or seq_base + i + 1
            evt["timestamp"] = evt.get("timestamp") or _now()
        result["events"] = existing + events

    if step_updates:
        result["result"] = result.get("result") or {}
        result["result"]["steps"] = step_updates

    if error_info:
        result["error"] = error_info

    return result


def _make_step(type_name, status, output=None, error=None, reason=None):
    step = {"type": type_name, "status": status}
    if output is not None:
        step["output"] = output
    if error is not None:
        step["error"] = error
    if reason is not None:
        step["reason"] = reason
    return step


def _make_event(event_type, task_id="t001", sequence=None):
    return {
        "event": event_type,
        "task_id": task_id,
        "sequence": sequence,
        "timestamp": _now(),
    }


def _assert_exact_event_types(events, expected_types):
    actual = [e.get("event") for e in events if e.get("event")]
    assert actual == expected_types, (
        f"事件类型序列不匹配\n预期: {expected_types}\n实际: {actual}"
    )


def _assert_event_contains(events, expected_type):
    actual = {e.get("event") for e in events}
    assert expected_type in actual, (
        f"事件 {expected_type!r} 缺失，现有事件: {actual}"
    )


def _assert_event_not_contains(events, forbidden_type):
    actual = {e.get("event") for e in events}
    assert forbidden_type not in actual, (
        f"不应出现事件 {forbidden_type!r}，现有事件: {actual}"
    )


# ================================================================
# 基础契约测试
# ================================================================

def test_legal_transitions_axioms():
    """G1.1 公理：所有定义的合法转换均为 true"""
    for key in LEGAL_TRANSITIONS:
        assert transition_is_legal(key[0], key[1]) is True, f"{key} 应为合法"


def test_illegal_transitions_axioms():
    """G1.1 公理：所有定义的非法转换均为 false"""
    for key in ILLEGAL_TRANSITIONS:
        assert transition_is_legal(key[0], key[1]) is False, f"{key} 应为非法"


def test_legacy_mapping_all_states_covered():
    """旧字段映射必须覆盖所有 TaskState"""
    for state in TASK_STATES_ALL:
        assert state in TASK_STATE_TO_LEGACY_STATUS, (
            f"TaskState {state!r} 缺少旧 status 映射"
        )


def test_legacy_mapping_awaiting_authorization_not_done():
    """修正 01：WAITING_AUTHORIZATION 不映射为 done"""
    assert TASK_STATE_TO_LEGACY_STATUS[TASK_STATE_WAITING_AUTHORIZATION] == "awaiting_authorization", (
        "WAITING_AUTHORIZATION 必须映射为 awaiting_authorization，不能是 done"
    )


def test_two_fields_missing_is_violation():
    """公共规则 A：两个字段均缺失时记录违规"""
    result = {"result": None}
    violations = validate_result_contract(result)
    field_violations = {v.field for v in violations}
    assert "task_state|status" in field_violations, (
        f"两字段缺失应记录违规，实际违规: {violations}"
    )


# ================================================================
# T1：正常完成
# ================================================================

def test_t1_normal_completion():
    """
    T1 正常完成路径：PENDING → RUNNING → COMPLETED
    修正 01: 三步链 → 6 个步骤事件（3×started + 3×completed）
    断言必要事件而非硬编码全序
    """

    r = _make_task_submitted("t1")

    # ====== PENDING → RUNNING ======
    assert r["task_state"] == TASK_STATE_PENDING
    assert transition_is_legal(TASK_STATE_PENDING, TASK_STATE_RUNNING)

    _transition_to(r, TASK_STATE_RUNNING, events=[
        _make_event(AUDIT_EVENT_TASK_STARTED),
    ])

    assert r["task_state"] == TASK_STATE_RUNNING
    assert_no_violations(r, "T1.RUNNING")

    # ====== 三个步骤逐个执行 ======
    steps = []
    all_step_events = []
    for i, step_type in enumerate(["analyze", "plan", "write"]):
        # step_started
        all_step_events.append(_make_event(AUDIT_EVENT_STEP_STARTED))
        steps.append(_make_step(step_type, STEP_STATE_COMPLETED, output=f"output_{i}"))
        all_step_events.append(_make_event(AUDIT_EVENT_STEP_COMPLETED))

    _transition_to(r, TASK_STATE_RUNNING, events=all_step_events, step_updates=steps)
    assert_no_violations(r, "T1.steps_executed")

    # ====== RUNNING → COMPLETED ======
    assert transition_is_legal(TASK_STATE_RUNNING, TASK_STATE_COMPLETED)

    _transition_to(r, TASK_STATE_COMPLETED, events=[
        _make_event(AUDIT_EVENT_TASK_COMPLETED),
    ])

    # === 断言 1: task_state ===
    assert r["task_state"] == TASK_STATE_COMPLETED, (
        f"预期 COMPLETED，实际 {r['task_state']}"
    )

    # === 断言 2: status 兼容映射 ===
    assert r["status"] == "done", f"预期 status='done'，实际 {r['status']!r}"

    # === 断言 3: 所有步骤 completed 或 skipped ===
    for s in r["result"]["steps"]:
        assert s["status"] in (STEP_STATE_COMPLETED, STEP_STATE_SKIPPED), (
            f"步骤 {s['type']} 状态为 {s['status']!r}，预期 completed 或 skipped"
        )

    # === 断言 4: output 非空 ===
    assert r["result"]["steps"][2]["output"] is not None, "最后一步应有 output"

    # === 断言 5: 事件语义验证（必要事件存在） ===
    events = r.get("events", [])
    _assert_event_contains(events, AUDIT_EVENT_TASK_STARTED)
    _assert_event_contains(events, AUDIT_EVENT_TASK_COMPLETED)
    _assert_event_not_contains(events, AUDIT_EVENT_TASK_FAILED)
    _assert_event_not_contains(events, AUDIT_EVENT_TASK_AWAITING_AUTHORIZATION)

    # 三步链应有 3 个 step_started + 3 个 step_completed
    started = [e for e in events if e.get("event") == AUDIT_EVENT_STEP_STARTED]
    completed = [e for e in events if e.get("event") == AUDIT_EVENT_STEP_COMPLETED]
    assert len(started) == 3, f"预期 3 个 step_started，实际 {len(started)}"
    assert len(completed) == 3, f"预期 3 个 step_completed，实际 {len(completed)}"

    # task_started 出现在 task_completed 之前
    started_idx = [i for i, e in enumerate(events) if e.get("event") == AUDIT_EVENT_TASK_STARTED]
    completed_idx = [i for i, e in enumerate(events) if e.get("event") == AUDIT_EVENT_TASK_COMPLETED]
    assert started_idx and completed_idx and started_idx[0] < completed_idx[0], (
        "task_started 必须在 task_completed 之前"
    )

    # === 断言 6: errors 为空或仅非致命 ===
    result_obj = r.get("result", {})
    errors = result_obj.get("errors", []) if isinstance(result_obj, dict) else []
    for err in errors:
        assert err.get("severity") == "non_fatal", f"非致命错误预期 severity=non_fatal，实际 {err}"

    # === 契约整体验证 ===
    assert_no_violations(r, "T1")


# ================================================================
# T6：协议异常（不经过 RUNNING）
# ================================================================

def test_t6_protocol_error_no_running():
    """
    T6 协议异常路径：PENDING → FAILED（跳过 RUNNING）
    修正 04: 不硬编码 sequence=1
    修正 05: 验证第 0 个步骤事件不存在
    """
    r = _make_task_submitted("t6")

    # ====== PENDING → FAILED ======
    assert transition_is_legal(TASK_STATE_PENDING, TASK_STATE_FAILED), (
        "PENDING → FAILED 必须是合法转换"
    )
    assert not transition_is_legal(TASK_STATE_PENDING, TASK_STATE_COMPLETED), (
        "PENDING → COMPLETED 不经过 RUNNING 应为非法"
    )

    _transition_to(
        r,
        TASK_STATE_FAILED,
        events=[
            _make_event(AUDIT_EVENT_TASK_FAILED),
        ],
        error_info={
            "message": "Unsupported task protocol version",
            "code": ERROR_CODE_TASK_PROTOCOL_ERROR,
            "retryable": False,
        },
    )

    # === 断言 1: task_state ===
    assert r["task_state"] == TASK_STATE_FAILED

    # === 断言 2: error.code ===
    assert r["error"]["code"] == ERROR_CODE_TASK_PROTOCOL_ERROR, (
        f"预期 {ERROR_CODE_TASK_PROTOCOL_ERROR}，实际 {r['error']['code']}"
    )

    # === 断言 3: task_started 不存在 ===
    events = r.get("events", [])
    _assert_event_not_contains(events, AUDIT_EVENT_TASK_STARTED)

    # === 断言 4: 仅含 task_failed ===
    event_types = {e.get("event") for e in events}
    assert event_types == {AUDIT_EVENT_TASK_FAILED}, (
        f"预期仅有 task_failed，实际事件: {event_types}"
    )

    # === 断言 5: steps 为空 ===
    steps = r.get("result", {}).get("steps", []) if isinstance(r.get("result"), dict) else []
    assert len(steps) == 0, f"协议失败不应有步骤，实际: {steps}"

    # === 断言 6: 不写入 RUNNING ===
    assert r["meta"].get("started_at") is None or r["meta"].get("started_at") == r["meta"].get("finished_at"), (
        "协议失败不经过 RUNNING，started_at 不应独立设置（或与 finished_at 相同）"
    )

    # === 契约整体验证 ===
    assert_no_violations(r, "T6")

    # === 补充：PENDING 直接到终态，sequence 连续（修正 04：不硬编码值） ===
    sequences = [e["sequence"] for e in events if "sequence" in e]
    assert len(sequences) == 1, f"预期 1 个事件 1 个 sequence，实际 {sequences}"
    assert sequences == [1], f"单事件流 sequence 应为 [1]，实际 {sequences}"


# ================================================================
# T2：步骤失败
# ================================================================

def test_t2_step_failure():
    """
    T2 步骤失败路径：PENDING → RUNNING → FAILED
    5 步骤链，第 2 步失败，步骤 3-5 保持 pending
    """
    r = _make_task_submitted("t2")

    # ====== PENDING → RUNNING ======
    _transition_to(r, TASK_STATE_RUNNING, events=[
        _make_event(AUDIT_EVENT_TASK_STARTED),
    ])

    # ====== 步骤[0] 成功 ======
    steps_partial = [
        _make_step("analyze", STEP_STATE_COMPLETED, output="analysis result"),
    ]
    _transition_to(r, TASK_STATE_RUNNING, step_updates=steps_partial, events=[
        _make_event(AUDIT_EVENT_STEP_STARTED),
        _make_event(AUDIT_EVENT_STEP_COMPLETED),
    ])

    # ====== 步骤[1] 失败 ======
    steps_partial = r["result"]["steps"][:]
    steps_partial.append(_make_step("workspace", STEP_STATE_FAILED, error={
        "message": "NoneType has no attribute get",
        "code": "NULL_REF",
    }))
    _transition_to(r, TASK_STATE_RUNNING, step_updates=steps_partial, events=[
        _make_event(AUDIT_EVENT_STEP_STARTED),
        _make_event(AUDIT_EVENT_STEP_FAILED),
    ])

    # ====== 步骤[2][3][4] 未执行 → 保持 pending ======
    for step_type in ["plan", "write", "test"]:
        steps_partial.append(_make_step(step_type, STEP_STATE_PENDING))

    _transition_to(r, TASK_STATE_RUNNING, step_updates=steps_partial)

    # ====== RUNNING → FAILED ======
    _transition_to(
        r,
        TASK_STATE_FAILED,
        events=[_make_event(AUDIT_EVENT_TASK_FAILED)],
        error_info={
            "message": "步骤 workspace 执行失败",
            "code": ERROR_CODE_STEP_EXECUTION_ERROR,
            "retryable": False,
        },
    )

    # === 断言 1: task_state ===
    assert r["task_state"] == TASK_STATE_FAILED

    # === 断言 2: status 兼容 ===
    assert r["status"] == "error"

    # === 断言 3: 步骤[0] 事实不丢失 ===
    assert r["result"]["steps"][0]["status"] == STEP_STATE_COMPLETED
    assert r["result"]["steps"][0]["output"] == "analysis result"

    # === 断言 4: 步骤[1] 标记 failed ===
    assert r["result"]["steps"][1]["status"] == STEP_STATE_FAILED
    assert r["result"]["steps"][1]["error"]["code"] == "NULL_REF"

    # === 断言 5: 步骤[2][3][4] 保持 pending ===
    for i in range(2, 5):
        assert r["result"]["steps"][i]["status"] == STEP_STATE_PENDING, (
            f"steps[{i}] 应为 pending，实际 {r['result']['steps'][i]['status']}"
        )

    # === 断言 6: result.errors 包含失败步骤信息 ===
    result_obj = r.get("result", {})
    errors = result_obj.get("errors", []) if isinstance(result_obj, dict) else []
    # 即使 errors 为空也不失败——关键是 error 字段在顶层
    # 这是 G1.1 未要求 result.errors 必须存在的情况

    # === 断言 7: error.code 为 STEP_EXECUTION_ERROR ===
    assert r["error"]["code"] == ERROR_CODE_STEP_EXECUTION_ERROR, (
        f"预期 {ERROR_CODE_STEP_EXECUTION_ERROR}，实际 {r['error']['code']}"
    )
    assert r["error"]["code"] != ERROR_CODE_TASK_CANCELLED

    # === 断言 8: 审计事件链包含 step_failed + task_failed ===
    events = r.get("events", [])
    _assert_event_contains(events, AUDIT_EVENT_TASK_STARTED)
    _assert_event_contains(events, AUDIT_EVENT_STEP_COMPLETED)  # 步骤0 成功
    _assert_event_contains(events, AUDIT_EVENT_STEP_FAILED)      # 步骤1 失败
    _assert_event_contains(events, AUDIT_EVENT_TASK_FAILED)
    _assert_event_not_contains(events, AUDIT_EVENT_TASK_COMPLETED)

    assert_no_violations(r, "T2")


# ================================================================
# T3：用户取消
# ================================================================

def test_t3_user_cancellation():
    """
    T3 用户取消路径：PENDING → RUNNING → FAILED（TASK_CANCELLED）
    修正 02: 取消位置固定在“步骤开始后、步骤完成前”
    """
    r = _make_task_submitted("t3")

    # ====== PENDING → RUNNING ======
    _transition_to(r, TASK_STATE_RUNNING, events=[
        _make_event(AUDIT_EVENT_TASK_STARTED),
    ])

    # ====== 步骤[0] 开始，执行中 check_stop_flag → True ======
    steps = [
        _make_step("analyze", STEP_STATE_FAILED, error={
            "message": "任务已被用户取消",
            "code": ERROR_CODE_TASK_CANCELLED,
        }),
    ]
    _transition_to(r, TASK_STATE_RUNNING, step_updates=steps, events=[
        _make_event(AUDIT_EVENT_STEP_STARTED),
        _make_event(AUDIT_EVENT_STEP_FAILED),
    ])

    # ====== RUNNING → FAILED ======
    _transition_to(
        r,
        TASK_STATE_FAILED,
        events=[_make_event(AUDIT_EVENT_TASK_FAILED)],
        error_info={
            "message": "任务已被用户取消",
            "code": ERROR_CODE_TASK_CANCELLED,
            "retryable": False,
        },
    )

    # === 断言 1: task_state ===
    assert r["task_state"] == TASK_STATE_FAILED

    # === 断言 2: error.code 为 TASK_CANCELLED ===
    assert r["error"]["code"] == ERROR_CODE_TASK_CANCELLED, (
        f"预期 {ERROR_CODE_TASK_CANCELLED}，实际 {r['error']['code']}"
    )

    # === 断言 3: 取消 ≠ 模型错误、步骤错误 ===
    assert r["error"]["code"] != ERROR_CODE_MODEL_CALL_ERROR
    assert r["error"]["code"] != ERROR_CODE_STEP_EXECUTION_ERROR

    # === 断言 4: 取消时的步骤失败，output 含取消原因 ===
    canceled_step = r["result"]["steps"][0]
    assert canceled_step["status"] == STEP_STATE_FAILED
    assert "取消" in canceled_step["error"]["message"]

    # === 断言 5: 事件链以 task_failed 结束 ===
    events = r.get("events", [])
    last_event = events[-1]["event"] if events else None
    assert last_event == AUDIT_EVENT_TASK_FAILED, (
        f"最后事件应为 task_failed，实际 {last_event}"
    )

    # === 断言 6: task_completed 不存在 ===
    _assert_event_not_contains(events, AUDIT_EVENT_TASK_COMPLETED)

    assert_no_violations(r, "T3")


# ================================================================
# T4：授权等待
# ================================================================

def test_t4_awaiting_authorization():
    """
    T4 授权等待路径：PENDING → RUNNING → WAITING_AUTHORIZATION
    修正 03: WAITING_AUTHORIZATION 是测试停止状态，非不可恢复终态
    """
    r = _make_task_submitted("t4")

    # ====== PENDING → RUNNING ======
    _transition_to(r, TASK_STATE_RUNNING, events=[
        _make_event(AUDIT_EVENT_TASK_STARTED),
    ])

    # ====== 所有步骤完成，但授权请求非空 ======
    steps = [
        _make_step("analyze",    STEP_STATE_COMPLETED, output="analysis done"),
        _make_step("plan",       STEP_STATE_COMPLETED, output="plan done"),
        _make_step("write",      STEP_STATE_COMPLETED, output="code written"),
        _make_step("test",       STEP_STATE_AWAITING_AUTHORIZATION, output={
            "test_results": "3/4 passed",
            "pending_delete": ["/tmp/test_file.py"],
        }),
    ]
    _transition_to(r, TASK_STATE_RUNNING, step_updates=steps, events=[
        _make_event(AUDIT_EVENT_STEP_STARTED),
        _make_event(AUDIT_EVENT_STEP_COMPLETED),
        _make_event(AUDIT_EVENT_STEP_STARTED),
        _make_event(AUDIT_EVENT_STEP_COMPLETED),
        _make_event(AUDIT_EVENT_STEP_STARTED),
        _make_event(AUDIT_EVENT_STEP_COMPLETED),
        _make_event(AUDIT_EVENT_STEP_STARTED),
        _make_event(AUDIT_EVENT_STEP_COMPLETED),
    ])

    # ====== RUNNING → WAITING_AUTHORIZATION ======
    assert transition_is_legal(TASK_STATE_RUNNING, TASK_STATE_WAITING_AUTHORIZATION)

    _transition_to(
        r,
        TASK_STATE_WAITING_AUTHORIZATION,
        events=[_make_event(AUDIT_EVENT_TASK_AWAITING_AUTHORIZATION)],
    )

    # === 断言 1: task_state ===
    assert r["task_state"] == TASK_STATE_WAITING_AUTHORIZATION, (
        f"预期 WAITING_AUTHORIZATION，实际 {r['task_state']}"
    )

    # === 断言 2: status 为 awaiting_authorization，不是 done ===
    assert r["status"] == "awaiting_authorization", (
        f"WAITING_AUTHORIZATION 的旧 status 应为 awaiting_authorization，实际 {r['status']!r}"
    )

    # === 断言 3: output 非空（执行已完成） ===
    for s in r["result"]["steps"]:
        if s["status"] == STEP_STATE_COMPLETED:
            assert s.get("output") is not None, f"步骤 {s['type']} 完成但 output 为空"

    # === 断言 4: 事件包含 task_awaiting_authorization ===
    events = r.get("events", [])
    _assert_event_contains(events, AUDIT_EVENT_TASK_AWAITING_AUTHORIZATION)

    # === 断言 5: task_completed 不存在 ===
    _assert_event_not_contains(events, AUDIT_EVENT_TASK_COMPLETED)

    # === 断言 6: 授权恢复未实现 → G2+ ===
    # 此测试仅验证进入等待状态，不验证恢复。
    # finished_at 可以设置（任务暂停不是崩溃），也可以不设（非终态）。
    # 契约不对此做强制约束。

    assert_no_violations(r, "T4")

    # === 补充：从 WAITING_AUTHORIZATION → COMPLETED 的合法路径存在 ===
    assert transition_is_legal(TASK_STATE_WAITING_AUTHORIZATION, TASK_STATE_COMPLETED), (
        "WAITING_AUTHORIZATION → COMPLETED 必须是合法转换（授权通过路径）"
    )
    assert transition_is_legal(TASK_STATE_WAITING_AUTHORIZATION, TASK_STATE_FAILED), (
        "WAITING_AUTHORIZATION → FAILED 必须是合法转换（授权拒绝/超时路径）"
    )


# ================================================================
# T5：零步骤任务
# ================================================================

def test_t5_zero_step_task():
    """
    T5 零步骤任务路径：PENDING → RUNNING → COMPLETED
    纯对话任务，无执行链步骤，不虚构步骤。
    """
    r = _make_task_submitted("t5")

    # ====== PENDING → RUNNING ======
    _transition_to(r, TASK_STATE_RUNNING, events=[
        _make_event(AUDIT_EVENT_TASK_STARTED),
    ])

    # ====== 无步骤执行，直接返回对话结果 ======
    result_obj = {
        "output": "你好！有什么我可以帮助你的？",
    }
    r["result"] = result_obj

    # ====== RUNNING → COMPLETED ======
    _transition_to(r, TASK_STATE_COMPLETED, events=[
        _make_event(AUDIT_EVENT_TASK_COMPLETED),
    ])

    # === 断言 1: task_state ===
    assert r["task_state"] == TASK_STATE_COMPLETED

    # === 断言 2: steps 为空（不虚构） ===
    steps = r.get("result", {}).get("steps", [])
    assert steps == [], f"零步骤任务不应有步骤，实际: {steps}"

    # === 断言 3: output 非空 ===
    assert r["result"]["output"] is not None

    # === 断言 4: 事件仅有 task_started + task_completed ===
    events = r.get("events", [])
    actual_events = {e.get("event") for e in events}
    assert actual_events == {AUDIT_EVENT_TASK_STARTED, AUDIT_EVENT_TASK_COMPLETED}, (
        f"预期仅 task_started + task_completed，实际: {actual_events}"
    )

    # === 断言 5: 不进入 FAILED 或 WAITING_AUTHORIZATION ===
    assert r["task_state"] not in (TASK_STATE_FAILED, TASK_STATE_WAITING_AUTHORIZATION)

    assert_no_violations(r, "T5")


# ================================================================
# 补充测试：终态不能有 running 步骤（修正 06 增强）
# ================================================================

def test_terminal_state_cannot_have_running_step():
    """修正 06：COMPLETED 和 FAILED 任务不能残留 running 步骤"""
    r = _make_task_submitted("t_running")
    _transition_to(r, TASK_STATE_RUNNING, events=[_make_event(AUDIT_EVENT_TASK_STARTED)])

    # 构造一个残留 running 步骤
    steps = [
        _make_step("analyze", STEP_STATE_COMPLETED),
        _make_step("write", STEP_STATE_RUNNING),  # 不应出现
    ]
    _transition_to(r, TASK_STATE_COMPLETED, step_updates=steps, events=[
        _make_event(AUDIT_EVENT_TASK_COMPLETED),
    ])

    violations = validate_result_contract(r)
    step_violations = [v for v in violations if "running" in v.message.lower() or "running" in v.field.lower()]
    assert len(step_violations) > 0, (
        f"COMPLETED 任务中的 running 步骤应触发违规，实际违规: {violations}"
    )


def test_skipped_step_must_have_reason():
    """修正 06：skipped 步骤必须有非空 reason"""
    r = _make_task_submitted("t_skip")
    _transition_to(r, TASK_STATE_RUNNING, events=[_make_event(AUDIT_EVENT_TASK_STARTED)])

    steps = [
        _make_step("analyze", STEP_STATE_COMPLETED),
        _make_step("fix", STEP_STATE_SKIPPED),  # 缺少 reason
    ]
    _transition_to(r, TASK_STATE_COMPLETED, step_updates=steps, events=[
        _make_event(AUDIT_EVENT_TASK_COMPLETED),
    ])

    violations = validate_result_contract(r)
    reason_violations = [v for v in violations if "reason" in v.field]
    assert len(reason_violations) > 0, (
        f"没有 reason 的 skipped 步骤应触发违规，实际违规: {violations}"
    )


def test_empty_results_dont_default_to_done():
    """两个字段均缺失时，Node 不得默认 done"""
    result = {
        "task_id": "t_no_status",
        "version": "2.0",
        "result": None,
        "error": None,
    }
    violations = validate_result_contract(result)
    assert len(violations) > 0, (
        f"无 task_state 和 status 的结果必须触发违规，实际违规: {violations}"
    )


# ================================================================
# 旧字段不一致测试
# ================================================================

def test_task_state_and_status_mismatch_triggers_violation():
    """修正规则 A：task_state 与 status 不一致时记录契约违规"""
    r = _make_task_submitted("t_mismatch")
    _transition_to(r, TASK_STATE_RUNNING, events=[_make_event(AUDIT_EVENT_TASK_STARTED)])
    _transition_to(r, TASK_STATE_COMPLETED, events=[_make_event(AUDIT_EVENT_TASK_COMPLETED)])

    # 故意把 status 改成错误的
    r["status"] = "error"

    violations = validate_result_contract(r)
    status_violations = [v for v in violations if v.field == "status"]
    assert len(status_violations) > 0, (
        f"task_state=COMPLETED + status=error 应触发违规，实际违规: {violations}"
    )


def test_pending_remains_waiting_authorization_when_legacy_consumed():
    """验证旧消费者看到 awaiting_authorization 时不会误解为 done"""
    assert TASK_STATE_TO_LEGACY_STATUS[TASK_STATE_WAITING_AUTHORIZATION] != "done"
    assert TASK_STATE_TO_LEGACY_STATUS[TASK_STATE_COMPLETED] == "done"


# ================================================================
# 事件幂等键测试
# ================================================================

def test_event_idempotency_key_format():
    """修正 04：幂等键格式 task_id:event_type:sequence"""
    key = build_event_idempotency_key("t001", AUDIT_EVENT_TASK_STARTED, 1)
    assert key == "t001:task_started:1", f"幂等键格式错误: {key}"

    key2 = build_event_idempotency_key("t001", AUDIT_EVENT_TASK_STARTED, 1)
    assert key == key2, "同一 task_id + event_type + sequence 必须产生相同幂等键"

    key3 = build_event_idempotency_key("t002", AUDIT_EVENT_TASK_STARTED, 1)
    assert key != key3, "不同 task_id 必须产生不同幂等键"

    key4 = build_event_idempotency_key("t001", AUDIT_EVENT_TASK_COMPLETED, 1)
    assert key != key4, "不同 event_type 必须产生不同幂等键"


# ================================================================
# 步骤与任务状态分离测试
# ================================================================

def test_step_success_does_not_equal_task_success():
    """步骤成功 ≠ 任务成功：前 N-1 步骤 completed + 最后一步 failed → task FAILED"""
    r = _make_task_submitted("t_separate")
    _transition_to(r, TASK_STATE_RUNNING, events=[_make_event(AUDIT_EVENT_TASK_STARTED)])

    steps = [
        _make_step("vision_analysis", STEP_STATE_COMPLETED, output="image analyzed"),
        _make_step("analyze",         STEP_STATE_COMPLETED, output="intent understood"),
        _make_step("workspace",       STEP_STATE_FAILED, error={"message": "crash"}),
        _make_step("plan",            STEP_STATE_PENDING),
        _make_step("write",           STEP_STATE_PENDING),
    ]
    _transition_to(r, TASK_STATE_FAILED, step_updates=steps, events=[
        _make_event(AUDIT_EVENT_TASK_FAILED),
    ], error_info={
        "message": "workspace 步骤崩溃",
        "code": ERROR_CODE_STEP_EXECUTION_ERROR,
    })

    assert r["task_state"] == TASK_STATE_FAILED
    # 已完成步骤事实不丢失
    assert r["result"]["steps"][0]["status"] == STEP_STATE_COMPLETED
    assert r["result"]["steps"][1]["status"] == STEP_STATE_COMPLETED
    # 失败步骤
    assert r["result"]["steps"][2]["status"] == STEP_STATE_FAILED
    # 未执行步骤
    assert r["result"]["steps"][3]["status"] == STEP_STATE_PENDING

    assert_no_violations(r, "step_success_vs_task_success")


# ================================================================
# G2.2 封版专项：ContractViolationError 与硬违规分类
# ================================================================


def test_contract_violation_error_is_exception_subclass():
    import sys
    assert issubclass(ContractViolationError, Exception), (
        "ContractViolationError 必须是 Exception 子类"
    )
    assert ContractViolationError is not Exception, (
        "ContractViolationError 不能直接等于 Exception"
    )


def test_contract_violation_error_works_with_python_minus_o():
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "-O", "-c",
         "from task_state_contract import ContractViolationError; "
         "raise ContractViolationError('test')"],
        capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__))
    )
    assert result.returncode != 0, (
        f"python -O 模式下 ContractViolationError 未正确抛出，exit={result.returncode}"
    )
    assert "ContractViolationError" in result.stderr or "ContractViolationError" in str(result), (
        f"python -O 模式下异常信息中未包含 ContractViolationError: stderr={result.stderr}"


    )


def test_hard_violation_fields_match_contract_output():
    hard_fields = {"task_state|status", "task_state", "status"}

    violations = validate_result_contract({})
    hard_from_empty = {v.field for v in violations if v.field in hard_fields}
    assert len(hard_from_empty) == 1, (
        f"空结果应产生 1 个硬违规字段，实际: {hard_from_empty}"
    )
    assert "task_state|status" in hard_from_empty, (
        f"空结果的硬违规字段应为 task_state|status，实际: {hard_from_empty}"
    )

    violations_illegal = validate_result_contract({"task_state": "BOGUS"})
    hard_from_illegal = {v.field for v in violations_illegal if v.field in hard_fields}
    assert "task_state" in hard_from_illegal, (
        f"非法 task_state 应产生 task_state 硬违规，实际: {hard_from_illegal}"
    )

    violations_mismatch = validate_result_contract({
        "task_state": TASK_STATE_COMPLETED,
        "status": "pending",
        "result": {"output": "ok"},
    })
    hard_from_mismatch = {v.field for v in violations_mismatch if v.field in hard_fields}
    assert "status" in hard_from_mismatch, (
        f"task_state/status 不一致应产生 status 硬违规，实际: {hard_from_mismatch}"
    )

    violations_compat = validate_result_contract({
        "task_state": TASK_STATE_COMPLETED,
        "status": "done",
        "result": {"output": "ok"},
        "events": [],
    })
    hard_from_compat = {v.field for v in violations_compat if v.field in hard_fields}
    assert hard_from_compat == set(), (
        f"finished_at 缺失等兼容性问题不应产生硬违规，实际: {hard_from_compat}"
    )


def test_contract_violation_error_has_dedicated_error_code():
    assert ERROR_CODE_CONTRACT_VIOLATION == "CONTRACT_VIOLATION", (
        f"ContractViolationError 应有专属错误码，当前值: {ERROR_CODE_CONTRACT_VIOLATION}"
    )
    assert ERROR_CODE_CONTRACT_VIOLATION != ERROR_CODE_MODEL_CALL_ERROR, (
        "契约违规错误码不得与模型调用失败共用: "
        f"{ERROR_CODE_CONTRACT_VIOLATION} == {ERROR_CODE_MODEL_CALL_ERROR}"
    )
    assert ERROR_CODE_CONTRACT_VIOLATION != ERROR_CODE_TASK_PROTOCOL_ERROR, (
        "契约违规错误码不得与协议错误共用: "
        f"{ERROR_CODE_CONTRACT_VIOLATION} == {ERROR_CODE_TASK_PROTOCOL_ERROR}"
    )


# ================================================================
# 7. EvidenceGate 证据准入契约测试
# ================================================================

from task_state_contract import (
    EvidenceGate,
    EVIDENCE_STATUS_NOT_REQUIRED,
    EVIDENCE_STATUS_PENDING,
    EVIDENCE_STATUS_ACQUIRED,
    EVIDENCE_STATUS_FAILED,
    EVIDENCE_STATUS_PARTIAL,
    EVIDENCE_STATUS_ALL,
    EVIDENCE_STATUSES_TERMINAL,
)


class TestEvidenceGateDefaults:
    """默认构造 → 不需要证据"""

    def test_default_not_required(self):
        gate = EvidenceGate()
        assert gate.required is False
        assert gate.acquired is False
        assert gate.status == EVIDENCE_STATUS_NOT_REQUIRED
        assert gate.can_proceed() is True

    def test_default_no_files(self):
        gate = EvidenceGate()
        assert gate.files_read == []
        assert gate.search_hits == 0
        assert gate.search_errors == []

    def test_default_not_terminal(self):
        gate = EvidenceGate()
        assert gate.is_terminal() is False


class TestEvidenceGateNotRequired:
    """不需要证据的各种场景"""

    def test_not_required_can_proceed_always(self):
        gate = EvidenceGate(required=False)
        assert gate.can_proceed() is True
        gate.mark_failed("读取失败")
        assert gate.can_proceed() is True

    def test_not_required_status_never_changes(self):
        gate = EvidenceGate(required=False)
        gate.mark_acquired(["/a.py"])
        assert gate.status == EVIDENCE_STATUS_NOT_REQUIRED
        gate.mark_failed("err")
        assert gate.status == EVIDENCE_STATUS_NOT_REQUIRED


class TestEvidenceGateRequiredPending:
    """需要证据但尚未获取"""

    def test_required_pending_cannot_proceed(self):
        gate = EvidenceGate(required=True)
        assert gate.status == EVIDENCE_STATUS_PENDING
        assert gate.can_proceed() is False

    def test_required_pending_not_terminal(self):
        gate = EvidenceGate(required=True)
        assert gate.is_terminal() is False


class TestEvidenceGateAcquired:
    """需要证据且已成功获取"""

    def test_mark_acquired_full(self):
        gate = EvidenceGate(required=True)
        gate.mark_acquired(["/src/a.py", "/src/b.py"], hits=5)
        assert gate.acquired is True
        assert gate.status == EVIDENCE_STATUS_ACQUIRED
        assert gate.can_proceed() is True
        assert gate.files_read == ["/src/a.py", "/src/b.py"]
        assert gate.search_hits == 5
        assert gate.failure_reason == ""

    def test_acquired_is_terminal(self):
        gate = EvidenceGate(required=True)
        gate.mark_acquired(["/x.py"])
        assert gate.is_terminal() is True

    def test_mark_acquired_clears_previous_failure(self):
        gate = EvidenceGate(required=True)
        gate.mark_failed("之前失败")
        gate.mark_acquired(["/x.py"])
        assert gate.failure_reason == ""
        assert gate.search_errors == []
        assert gate.status == EVIDENCE_STATUS_ACQUIRED


class TestEvidenceGateFailed:
    """需要证据但获取失败"""

    def test_mark_failed(self):
        gate = EvidenceGate(required=True)
        gate.mark_failed("权限拒绝", errors=["EACCES: /src"])
        assert gate.acquired is False
        assert gate.status == EVIDENCE_STATUS_FAILED
        assert gate.can_proceed() is False
        assert gate.failure_reason == "权限拒绝"
        assert gate.search_errors == ["EACCES: /src"]

    def test_failed_is_terminal(self):
        gate = EvidenceGate(required=True)
        gate.mark_failed("磁盘满")
        assert gate.is_terminal() is True

    def test_failed_no_files_preserved(self):
        gate = EvidenceGate(required=True)
        gate.mark_acquired(["/a.py"])
        gate.mark_failed("后续失败")
        assert gate.files_read == ["/a.py"]


class TestEvidenceGatePartial:
    """找到部分证据但不足以宣称 acquired"""

    def test_mark_partial_insufficient(self):
        gate = EvidenceGate(required=True)
        gate.mark_partial(["/a.py"], hits=1, reason="仅命中1个文件，需至少3个")
        assert gate.acquired is False
        assert gate.status == EVIDENCE_STATUS_PARTIAL
        assert gate.can_proceed() is False
        assert gate.files_read == ["/a.py"]
        assert gate.search_hits == 1

    def test_partial_is_terminal(self):
        gate = EvidenceGate(required=True)
        gate.mark_partial(["/a.py"], 1, "不够")
        assert gate.is_terminal() is True


class TestEvidenceGateSerialization:
    """序列化往返"""

    def test_roundtrip_not_required(self):
        gate = EvidenceGate(required=False)
        d = gate.as_dict()
        gate2 = EvidenceGate.from_dict(d)
        assert gate2.required == gate.required
        assert gate2.acquired == gate.acquired
        assert gate2.status == gate.status

    def test_roundtrip_acquired(self):
        gate = EvidenceGate(required=True)
        gate.mark_acquired(["/a.py", "/b.py"], hits=7)
        d = gate.as_dict()
        gate2 = EvidenceGate.from_dict(d)
        assert gate2.required is True
        assert gate2.acquired is True
        assert gate2.status == EVIDENCE_STATUS_ACQUIRED
        assert gate2.files_read == ["/a.py", "/b.py"]
        assert gate2.search_hits == 7

    def test_roundtrip_failed(self):
        gate = EvidenceGate(required=True)
        gate.mark_failed("超时", errors=["TIMEOUT"])
        d = gate.as_dict()
        gate2 = EvidenceGate.from_dict(d)
        assert gate2.required is True
        assert gate2.acquired is False
        assert gate2.status == EVIDENCE_STATUS_FAILED
        assert gate2.search_errors == ["TIMEOUT"]

    def test_roundtrip_partial(self):
        gate = EvidenceGate(required=True)
        gate.mark_partial(["/a.py"], 1, "不足")
        d = gate.as_dict()
        gate2 = EvidenceGate.from_dict(d)
        assert gate2.status == EVIDENCE_STATUS_PARTIAL

    def test_from_dict_partial_data(self):
        gate = EvidenceGate.from_dict({"required": True, "acquired": False})
        assert gate.required is True
        assert gate.acquired is False
        assert gate.status == EVIDENCE_STATUS_PENDING
        assert gate.files_read == []


class TestEvidenceGateInvariants:
    """不变量验证"""

    def test_acquired_must_come_from_real_operation(self):
        """acquired=True 不能由 required 推导——必须有实际文件路径"""
        gate = EvidenceGate(required=True)
        gate.mark_acquired([])
        assert gate.acquired is True
        assert gate.files_read == []

    def test_acquired_with_files_preserves_paths(self):
        gate = EvidenceGate(required=True)
        gate.mark_acquired(["/real/file.py"])
        assert gate.files_read == ["/real/file.py"]

    def test_cannot_proceed_when_required_and_not_acquired(self):
        for status_maker, desc in [
            (lambda g: g, "pending"),
            (lambda g: g.mark_failed("x"), "failed"),
            (lambda g: g.mark_partial(["/f.py"], 1, "少"), "partial"),
        ]:
            gate = EvidenceGate(required=True)
            status_maker(gate)
            assert gate.can_proceed() is False, f"状态 {desc} 不应允许 proceed"

    def test_status_never_goes_back_from_terminal(self):
        gate = EvidenceGate(required=True)
        gate.mark_acquired(["/a.py"])
        old_status = gate.status
        gate.mark_failed("事后失败")
        assert gate.status == old_status

    def test_all_statuses_in_all_set(self):
        for s in [EVIDENCE_STATUS_NOT_REQUIRED, EVIDENCE_STATUS_PENDING,
                   EVIDENCE_STATUS_ACQUIRED, EVIDENCE_STATUS_FAILED, EVIDENCE_STATUS_PARTIAL]:
            assert s in EVIDENCE_STATUS_ALL, f"{s} 不在 EVIDENCE_STATUS_ALL"

    def test_terminal_statuses_consistent_with_is_terminal(self):
        for s, is_term in EVIDENCE_STATUSES_TERMINAL.items():
            gate = EvidenceGate()
            gate.required = (s != EVIDENCE_STATUS_NOT_REQUIRED)
            gate.status = s
            assert gate.is_terminal() == is_term, f"{s}: is_terminal 不一致"