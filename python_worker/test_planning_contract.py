# -*- coding: utf-8 -*-
"""
============================================================
Planning Contract v1.0 — 契约测试
映射: AlphaPilot_Planning_Contract_v1.0 Section 6 (PT-01 ~ PT-17)
============================================================
仅测试已实现的策略层（不依赖 LLM / 外部服务）。
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from intent_router._planning_contract import (
    IMPL_PLAN_REQUIREMENT,
    SAFE_REDIRECTIONS,
    BLOCKED_REDIRECTIONS,
    get_impl_plan_requirement,
    validate_replan,
    needs_reauthorization,
)

PASS, FAIL = 0, 0


def ok(pt_id, desc):
    global PASS
    PASS += 1
    print(f"  ✅ {pt_id}: {desc}")


def nope(pt_id, desc, detail=""):
    global FAIL
    FAIL += 1
    print(f"  ❌ {pt_id}: {desc}")
    if detail:
        print(f"     └─ {detail}")


def assert_eq(pt, got, want, desc):
    if got == want:
        ok(pt, desc)
    else:
        nope(pt, desc, f"期望 {want!r}, 实际 {got!r}")


# ============================================================
# PT-07a: impl_plan_requirement=required 的意图
# ============================================================
def test_pt07a_required_intents():
    """所有会产生写入副作用的意图 MUST 返回 'required'"""
    print("\n[PT-07a] implementation_plan_requirement = required 对写入意图")
    required = {
        "write_code", "fix_code", "explain_and_fix", "refactor",
        "delete_files", "workspace_maintenance", "vision_analysis",
        "external_git",
    }
    for intent in required:
        got = get_impl_plan_requirement(intent)
        assert_eq("PT-07a", got, "required",
                  f"{intent} 应返回 'required', 实际 '{got}'")

    # PT-07a corollary: 这些意图的缺失 plan 应被阻断（策略层先验）
    for intent in required:
        got = IMPL_PLAN_REQUIREMENT.get(intent)
        assert_eq("PT-07a", got, "required",
                  f"IMPL_PLAN_REQUIREMENT[{intent}] == 'required'")


# ============================================================
# PT-07b: impl_plan_requirement=optional/not_applicable 的意图
# ============================================================
def test_pt07b_optional_not_applicable():
    """只读/纯对话意图 MUST 返回 optional 或 not_applicable"""
    print("\n[PT-07b] implementation_plan_requirement = optional / not_applicable")

    not_applicable = {"chat", "mentor_explain", "explain_code", "code_review"}
    for intent in not_applicable:
        got = get_impl_plan_requirement(intent)
        assert_eq("PT-07b", got, "not_applicable",
                  f"{intent} 应返回 'not_applicable', 实际 '{got}'")

    optional = {"analysis", "architecture", "generate_doc", "set_preference",
                "creative_writing"}
    for intent in optional:
        got = get_impl_plan_requirement(intent)
        assert_eq("PT-07b", got, "optional",
                  f"{intent} 应返回 'optional', 实际 '{got}'")


# ============================================================
# PT-08: 模型提出未允许的 intent 重定向 → 拒绝
# ============================================================
def test_pt08_blocked_redirections():
    """跨能力域/权限升级的重定向 MUST 被阻止"""
    print("\n[PT-08] 未允许的 intent 重定向 → 阻断")

    blocked_cases = [
        ("chat", "write_code"),
        ("chat", "delete_files"),
        ("mentor_explain", "write_code"),
        ("code_review", "write_code"),
        ("write_code", "delete_files"),
        ("write_code", "external_git"),
        ("fix_code", "external_git"),
    ]
    for old, new in blocked_cases:
        allowed, reason = validate_replan(old, new)
        if not allowed:
            ok("PT-08", f"{old} → {new} 正确阻断: {reason}")
        else:
            nope("PT-08", f"{old} → {new} 应被阻断, 但返回允许", f"reason={reason}")


def test_pt08_safe_redirections():
    """同能力域内的安全重定向 MUST 被允许"""
    print("\n[PT-08b] 安全重定向 → 允许")

    safe_cases = [
        ("write_code", "fix_code"),
        ("fix_code", "write_code"),
        ("architecture", "write_code"),
        ("analysis", "write_code"),
        ("analysis", "refactor"),
    ]
    for old, new in safe_cases:
        allowed, reason = validate_replan(old, new)
        if allowed and reason is None:
            ok("PT-08b", f"{old} → {new} 安全通过")
        else:
            nope("PT-08b", f"{old} → {new} 应允许安全转换",
                 f"allowed={allowed}, reason={reason}")


def test_pt08_same_intent():
    """同 intent 重定向 MUST 不被视为重规划"""
    print("\n[PT-08c] 同 intent 重定向 → 无操作")
    allowed, reason = validate_replan("write_code", "write_code")
    if allowed and reason is None:
        ok("PT-08c", "write_code → write_code 无操作通过")
    else:
        nope("PT-08c", f"同 intent 应无操作, allowed={allowed}, reason={reason}")


# ============================================================
# PT-09: 重规划新增操作对象 → 重新授权
# ============================================================
def test_pt09_needs_reauthorization():
    """重规划新增写入/删除/外部访问 MUST 触发重新授权"""
    print("\n[PT-09] 重规划新增操作对象 → 重新授权判定")

    reauth_cases = [
        ("chat", "write_code", True),
        ("chat", "delete_files", True),
        ("mentor_explain", "external_git", True),
        ("code_review", "delete_files", True),
        ("write_code", "delete_files", True),
        ("write_code", "external_git", True),
    ]
    for old, new, need in reauth_cases:
        got = needs_reauthorization(old, new)
        if got == need:
            ok("PT-09", f"{old} → {new} reauth={'需要' if need else '不需要'}")
        else:
            nope("PT-09", f"{old} → {new}",
                 f"期望 reauth={need}, 实际 {got}")

    # 同能力域内安全转换不应触发重授权
    no_reauth_cases = [
        ("write_code", "fix_code"),
        ("fix_code", "explain_and_fix"),
        ("architecture", "write_code"),
    ]
    for old, new in no_reauth_cases:
        got = needs_reauthorization(old, new)
        if not got:
            ok("PT-09b", f"{old} → {new} 无需重新授权")
        else:
            nope("PT-09b", f"{old} → {new}", f"不应触发重授权, 实际 needs_reauth=True")


# ============================================================
# PT-10: 计划声明能力但实际未授权 → 独立于本模块
# ============================================================
def test_pt10_capability_isf_deny():
    """PT-10 依赖 R6 / EvidenceGate，本模块仅断言策略表不授予能力"""
    print("\n[PT-10] 计划声明能力 ≠ 操作授权（策略表边界检查）")
    # 策略表本身不包含任何"授权"字段，仅表达规划约束
    # 能力/副作用授权由独立的安全契约保证
    # 此处确认 BLOCKED_REDIRECTIONS 包含能力升级路径
    blocked = BLOCKED_REDIRECTIONS
    upgrade_paths = [
        ("chat", "write_code"),   # read → write
        ("chat", "delete_files"),  # read → delete
        ("chat", "external_git"),  # read → git
        ("write_code", "delete_files"),  # write → delete
        ("write_code", "external_git"),  # write → git
    ]
    for pair in upgrade_paths:
        if pair in blocked:
            ok("PT-10", f"{pair[0]} → {pair[1]} 在 BLACKED_REDIRECTIONS 中")
        else:
            nope("PT-10", f"{pair[0]} → {pair[1]} 应从策略表阻断能力升级")


# ============================================================
# PT-14: 兼容转换（策略层）
# ============================================================
def test_pt14_policy_consistency():
    """PT-14: 确保策略表与 IMPL_PLAN_REQUIREMENT 的意图覆盖一致"""
    print("\n[PT-14] 策略表与需求表覆盖一致性")
    # 所有在 IMPL_PLAN_REQUIREMENT 中的意图都应被 SAFE_REDIRECTIONS 或
    # BLOCKED_REDIRECTIONS 至少在某个方向覆盖（或显式标记为不需要）

    all_ints = set(IMPL_PLAN_REQUIREMENT.keys())
    # 收集所有被 SAFE_REDIRECTIONS 作为源的意图
    safe_sources = set(SAFE_REDIRECTIONS.keys())
    # 收集所有被 BLOCKED_REDIRECTIONS 作为源的意图
    blocked_sources = {p[0] for p in BLOCKED_REDIRECTIONS}
    # 所有在任意重定向中出现的意图
    redirected = safe_sources | blocked_sources | {p[1] for p in BLOCKED_REDIRECTIONS}

    for intent in sorted(all_ints):
        if intent in redirected:
            ok("PT-14", f"{intent} 在重定向策略中有覆盖")
        else:
            # 某些意图天然单步或无重定向场景（如 set_preference, creative_writing）
            print(f"  ⚠️  PT-14: {intent} 未在重定向策略中（可能无需重定向）")


# ============================================================
# PT-16: 重规划改变能力/工作区依赖 → 策略校验
# ============================================================
def test_pt16_replan_policy_coverage():
    """PT-16: 策略表覆盖所有常见的能力域变化"""
    print("\n[PT-16] 重规划策略覆盖能力域变化")
    # 写代码域: write_code, fix_code, explain_and_fix, refactor
    write_domain = {"write_code", "fix_code", "explain_and_fix", "refactor"}
    for src in write_domain:
        safe_targets = SAFE_REDIRECTIONS.get(src, set())
        for dst in write_domain:
            if src == dst:
                continue
            pair = (src, dst)
            if dst in safe_targets:
                ok("PT-16", f"{src} → {dst} 安全转换已允许")
            elif pair in BLOCKED_REDIRECTIONS:
                ok("PT-16", f"{src} → {dst} 阻断转换已记录")
            else:
                print(f"  ⚠️  PT-16: {src} → {dst} 未在安全/阻断表中（将走默认审核路径）")


# ============================================================
# PT-17: 不需要工作区的任务不强制 workspace
# ============================================================
def test_pt17_no_forced_workspace():
    """PT-17: 纯对话/只读意图不应要求 workspace 依赖（策略层先验）"""
    print("\n[PT-17] 不需要工作区的意图策略检查")
    no_workspace_intents = {"chat", "mentor_explain", "explain_code",
                            "creative_writing"}
    for intent in no_workspace_intents:
        req = get_impl_plan_requirement(intent)
        if req in ("not_applicable", "optional"):
            ok("PT-17", f"{intent} 策略不要求实施步骤 (impl_req={req})")
        else:
            nope("PT-17", f"{intent}", f"不应要求实施步骤, 实际 impl_req={req}")


# ============================================================
# PT-13: 只读/纯对话任务走简化路径
# ============================================================
def test_pt13_read_only_simplified():
    """PT-13: 只读任务策略层表现为 optional/not_applicable"""
    print("\n[PT-13] 只读/纯对话任务简化路径")
    read_only = {"chat", "mentor_explain", "explain_code", "code_review",
                 "analysis", "creative_writing"}
    for intent in read_only:
        req = get_impl_plan_requirement(intent)
        if req != "required":
            ok("PT-13", f"{intent} 不为 required ({req})")
        else:
            nope("PT-13", f"{intent}", "只读任务不应为 required")


# ============================================================
# PT-01: 缺少必需字段或字段类型错误
# ============================================================
def test_pt01_missing_required_fields():
    """"PT-01: 缺少必需字段 → 激活前拒绝计划"""
    print("\n[PT-01] 缺少必需字段或字段类型错误")

    from intent_router._plan_validator import validate_plan_fields

    # case 1: 空对象 → 失败
    r = validate_plan_fields({})
    if not r.valid and len(r.errors) >= 2:
        ok("PT-01", f"空 plan 被拒绝 ({len(r.errors)} 错误)")
    else:
        nope("PT-01", f"空 plan 应被拒绝, valid={r.valid}, errors={r.errors}")

    # case 2: 缺少 execution_chain
    r = validate_plan_fields({"intent": "write_code"})
    if not r.valid and any("execution_chain" in e for e in r.errors):
        ok("PT-01", "缺少 execution_chain 被检测")
    else:
        nope("PT-01", f"应检测到缺少 execution_chain, errors={r.errors}")

    # case 3: intent 类型错误
    r = validate_plan_fields({"intent": 123, "execution_chain": ["analyze", "write"]})
    if not r.valid:
        ok("PT-01", f"intent 类型错误被检测: {r.errors}")
    else:
        nope("PT-01", "intent 类型错误应被检测")

    # case 4: execution_chain 类型错误
    r = validate_plan_fields({"intent": "write_code", "execution_chain": "not_a_list"})
    if not r.valid:
        ok("PT-01", f"execution_chain 类型错误被检测: {r.errors}")
    else:
        nope("PT-01", "execution_chain 类型错误应被检测")

    # case 5: 最小有效 plan 通过
    r = validate_plan_fields({
        "intent": "write_code",
        "execution_chain": ["analyze", "plan", "write"],
        "mode": "ENGINEER_EXECUTE",
        "context_requirements": [],
        "capabilities": [],
        "side_effects": [],
        "approval": {"required": False, "before": []},
        "validation": [],
        "recovery": [],
    })
    if r.valid:
        ok("PT-01", "最小有效 plan 通过")
    else:
        nope("PT-01", f"最小有效 plan 应通过, errors={r.errors}")


def test_pt01_impl_plan_requirement_type():
    """implementation_plan_requirement 必须为合法值"""
    print("\n[PT-01b] implementation_plan_requirement 值校验")

    from intent_router._plan_validator import validate_plan_fields

    r = validate_plan_fields({
        "intent": "write_code",
        "execution_chain": ["write"],
        "implementation_plan_requirement": "INVALID_VALUE",
    })
    if not r.valid and any("implementation_plan_requirement" in e for e in r.errors):
        ok("PT-01b", "非法 impl_plan_requirement 值被拒绝")
    else:
        nope("PT-01b", f"应拒绝非法值, errors={r.errors}")

    for val in ("required", "optional", "not_applicable"):
        r = validate_plan_fields({
            "intent": "write_code",
            "execution_chain": ["write"],
            "implementation_plan_requirement": val,
        })
        if r.valid:
            ok("PT-01b", f"合法值 '{val}' 通过")
        else:
            nope("PT-01b", f"合法值 '{val}' 应通过, errors={r.errors}")


# ============================================================
# PT-02: step_id 重复、依赖不存在或依赖图有环
# ============================================================
def test_pt02_duplicate_step_id():
    """PT-02: step_id 重复 → 校验失败"""
    print("\n[PT-02] step_id 重复 / 依赖有效性 / 环检测")

    from intent_router._plan_validator import validate_steps

    r = validate_steps([
        {"id": "step-1", "type": "analyze", "input": {}},
        {"id": "step-1", "type": "plan", "input": {}},
        {"id": "step-2", "type": "write", "input": {}},
    ])
    if not r.valid and any("重复" in e for e in r.errors):
        ok("PT-02", "step_id 重复被检测")
    else:
        nope("PT-02", f"应检测到 step_id 重复, errors={r.errors}")


def test_pt02_missing_dependency():
    """PT-02: 依赖不存在 → 校验失败"""
    from intent_router._plan_validator import validate_dependencies

    r = validate_dependencies([
        {"id": "step-1", "type": "analyze", "input": {}, "depends_on": []},
        {"id": "step-2", "type": "write", "input": {}, "depends_on": ["step-99"]},
    ])
    if not r.valid and any("不存在" in e or "不存在的步骤" in e for e in r.errors):
        ok("PT-02", "依赖不存在的步骤被检测")
    else:
        nope("PT-02", f"应检测到依赖不存在, errors={r.errors}")


def test_pt02_dependency_cycle():
    """PT-02: 依赖图有环 → 校验失败"""
    from intent_router._plan_validator import validate_dependencies

    r = validate_dependencies([
        {"id": "step-1", "type": "analyze", "input": {}, "depends_on": ["step-3"]},
        {"id": "step-2", "type": "plan", "input": {}, "depends_on": ["step-1"]},
        {"id": "step-3", "type": "write", "input": {}, "depends_on": ["step-2"]},
    ])
    if not r.valid and any("环" in e for e in r.errors):
        ok("PT-02", "依赖图环被检测")
    else:
        nope("PT-02", f"应检测到依赖环, errors={r.errors}")


def test_pt02_valid_dependencies():
    """PT-02: 合法依赖通过校验"""
    from intent_router._plan_validator import validate_dependencies

    r = validate_dependencies([
        {"id": "step-1", "type": "analyze", "input": {}, "depends_on": []},
        {"id": "step-2", "type": "plan", "input": {}, "depends_on": ["step-1"]},
        {"id": "step-3", "type": "write", "input": {}, "depends_on": ["step-2"]},
        {"id": "step-4", "type": "test", "input": {}, "depends_on": ["step-3"]},
    ])
    if r.valid:
        ok("PT-02", "合法线性依赖图通过")
    else:
        nope("PT-02", f"合法依赖应通过, errors={r.errors}")


def test_pt02_invalid_step_type():
    """PT-02: 未知步骤类型 → 警告"""
    from intent_router._plan_validator import validate_steps

    r = validate_steps([
        {"id": "step-1", "type": "analyze", "input": {}},
        {"id": "step-2", "type": "__evil_step__", "input": {}},
    ])
    if not r.valid:
        ok("PT-02", f"未知步骤类型被拒绝: {r.errors}")
    else:
        nope("PT-02", "未知步骤类型应被拒绝")


# ============================================================
# PT-03: 前置步骤未成功完成 → 阻断依赖步骤启动
# ============================================================
def test_pt03_precondition_not_met():
    """PT-03: 前置步骤未完成 → 阻断"""
    print("\n[PT-03] 前置步骤未成功完成 → 阻断")

    from intent_router._plan_validator import check_preconditions

    # 依赖未完成
    r = check_preconditions(
        {"id": "step-2", "depends_on": ["step-1"]},
        completed_step_ids=set(),
        step_results={},
    )
    if not r.valid:
        ok("PT-03", "依赖步骤未完成被阻断")
    else:
        nope("PT-03", "应阻断未完成依赖")

    # 依赖已完成但失败
    r = check_preconditions(
        {"id": "step-2", "depends_on": ["step-1"]},
        completed_step_ids={"step-1"},
        step_results={"step-1": {"status": "FAILED", "success": False}},
    )
    if not r.valid:
        ok("PT-03", "依赖步骤失败被阻断")
    else:
        nope("PT-03", "应阻断失败依赖")

    # 正常通过
    r = check_preconditions(
        {"id": "step-2", "depends_on": ["step-1"]},
        completed_step_ids={"step-1"},
        step_results={"step-1": {"status": "COMPLETED", "success": True}},
    )
    if r.valid:
        ok("PT-03", "正常依赖通过")
    else:
        nope("PT-03", f"正常依赖应通过, errors={r.errors}")


# ============================================================
# PT-05: checker 未注册 → 不得判定任务成功
# ============================================================
def test_pt05_checker_not_registered():
    """PT-05: 未注册 checker → 返回失败"""
    print("\n[PT-05] checker 未注册 → 不得判定成功")

    from intent_router._checker_registry import run_checker

    r = run_checker("__nonexistent_checker__", {}, None, {})
    if not r.passed and "未注册" in r.evidence:
        ok("PT-05", "未注册 checker 返回失败")
    else:
        nope("PT-05", f"未注册 checker 应失败, passed={r.passed}, evidence={r.evidence}")


def test_pt05_checker_registered():
    """PT-05: 已注册 checker 正常执行"""
    from intent_router._checker_registry import run_checker, CHECKER_REGISTRY

    for checker_id in CHECKER_REGISTRY:
        r = run_checker(checker_id, {"kind": "none"}, None, {"meta": {}})
        if isinstance(r.passed, bool):
            ok("PT-05", f"checker '{checker_id}' 可执行")
        else:
            nope("PT-05", f"checker '{checker_id}' 返回异常: {r}")


# ============================================================
# PT-06: 必需验证条件未通过 → 不得判定任务成功
# ============================================================
def test_pt06_required_condition_failure():
    """PT-06: 必需条件失败 → all_passed=False"""
    print("\n[PT-06] 必需验证条件未通过 → 阻断完成")

    from intent_router._checker_registry import run_validation_conditions

    conditions = [
        {
            "checker": "step.completed",
            "target": {"step_id": "step-missing"},
            "expected": None,
            "required": True,
            "on_failure": "block_completion",
        }
    ]
    all_passed, results = run_validation_conditions(conditions, {"intermediate_results": []})
    if not all_passed and len(results) == 1 and not results[0].passed:
        ok("PT-06", f"必需条件失败正确阻断: {results[0].evidence[:60]}")
    else:
        nope("PT-06", f"应阻断, all_passed={all_passed}")


def test_pt06_non_required_condition_does_not_block():
    """PT-06: 非必需条件失败不阻断"""
    from intent_router._checker_registry import run_validation_conditions

    conditions = [
        {
            "checker": "step.completed",
            "target": {"step_id": "step-missing"},
            "expected": None,
            "required": False,
            "on_failure": "allow_completion",
        }
    ]
    all_passed, results = run_validation_conditions(conditions, {"intermediate_results": []})
    if all_passed and not results[0].passed:
        ok("PT-06", "非必需条件失败不阻断 (all_passed=True)")
    elif not all_passed:
        nope("PT-06", "非必需条件失败不应阻断")
    else:
        ok("PT-06", "非必需条件正确允许通过")


# ============================================================
# PT-15: 审计事件（校验结果可序列化）
# ============================================================
def test_pt15_audit_serializability():
    """PT-15: 校验结果可序列化为审计记录"""
    print("\n[PT-15] 审计事件可序列化")

    import json
    from intent_router._plan_validator import validate_plan_full, validate_steps
    from intent_router._checker_registry import run_checker

    # plan 校验结果序列化
    r = validate_plan_full({"intent": "chat", "execution_chain": ["respond"]})
    d = r.to_dict()
    try:
        j = json.dumps(d)
        ok("PT-15", f"校验结果可序列化 ({len(j)} bytes)")
    except Exception as e:
        nope("PT-15", f"序列化失败: {e}")

    # checker 结果序列化
    r = run_checker("file.exists", {"path": "/tmp/nonexistent"}, True, {})
    d = r.to_dict()
    try:
        j = json.dumps(d)
        ok("PT-15", f"checker 结果可序列化 ({len(j)} bytes)")
    except Exception as e:
        nope("PT-15", f"序列化失败: {e}")


# ============================================================
# 边缘情况测试
# ============================================================
def test_edge_unknown_intent():
    """未知意图默认返回 'required'（安全兜底）"""
    print("\n[Edge] 未知意图兜底策略")
    got = get_impl_plan_requirement("__nonexistent_intent__")
    assert_eq("Edge", got, "required",
              f"未知意图应兜底为 'required', 实际 '{got}'")


def test_edge_unknown_redirect():
    """未知意图重定向走默认审核路径"""
    allowed, reason = validate_replan("__unknown_1__", "__unknown_2__")
    if allowed and reason and "REVIEW" in reason:
        ok("Edge", f"未知意图重定向走审核路径: {reason}")
    else:
        nope("Edge", f"未知重定向应走审核路径", f"allowed={allowed}, reason={reason}")


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Planning Contract v1.0 — 契约测试")
    print("=" * 60)

    test_pt07a_required_intents()
    test_pt07b_optional_not_applicable()
    test_pt08_blocked_redirections()
    test_pt08_safe_redirections()
    test_pt08_same_intent()
    test_pt09_needs_reauthorization()
    test_pt10_capability_isf_deny()
    test_pt14_policy_consistency()
    test_pt16_replan_policy_coverage()
    test_pt17_no_forced_workspace()
    test_pt13_read_only_simplified()
    test_pt01_missing_required_fields()
    test_pt01_impl_plan_requirement_type()
    test_pt02_duplicate_step_id()
    test_pt02_missing_dependency()
    test_pt02_dependency_cycle()
    test_pt02_valid_dependencies()
    test_pt02_invalid_step_type()
    test_pt03_precondition_not_met()
    test_pt05_checker_not_registered()
    test_pt05_checker_registered()
    test_pt06_required_condition_failure()
    test_pt06_non_required_condition_does_not_block()
    test_pt15_audit_serializability()
    test_edge_unknown_intent()
    test_edge_unknown_redirect()

    print(f"\n{'=' * 60}")
    print(f"PASS={PASS}  FAIL={FAIL}")
    print(f"{'=' * 60}")
    sys.exit(0 if FAIL == 0 else 1)