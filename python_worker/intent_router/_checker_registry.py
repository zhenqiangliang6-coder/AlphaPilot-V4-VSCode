# -*- coding: utf-8 -*-
# intent_router/_checker_registry.py
# ---------------------------------------------------------
# Planning Contract v1.0 — Checker Registry（STEP_DISPATCHER 范式）
# PT-05 / PT-06: 验证器注册、执行与结果判定
# 纯注册表模块，不修改生产代码路径，不引入旁路端点
# ---------------------------------------------------------

from typing import Dict, List, Optional, Any, Callable, Tuple


# ============================================================
# Checker 签名: (target: dict, expected: Any, context: dict) -> CheckerResult
# ============================================================

class CheckerResult:
    """单个 checker 的执行结果。"""

    __slots__ = ("passed", "evidence", "detail")

    def __init__(self, passed: bool, evidence: str = "", detail: dict = None):
        self.passed = passed
        self.evidence = evidence
        self.detail = detail or {}

    def __repr__(self):
        return f"CheckerResult(passed={self.passed}, evidence={self.evidence[:60]!r})"

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "evidence": self.evidence,
            "detail": self.detail,
        }


CheckerFunc = Callable[[Dict[str, Any], Any, Dict[str, Any]], CheckerResult]


# ============================================================
# CHECKER_REGISTRY — 遵循 STEP_DISPATCHER 范式
# ============================================================

CHECKER_REGISTRY: Dict[str, CheckerFunc] = {}


def register_checker(checker_id: str):
    """注册装饰器 — 与 STEP_DISPATCHER 的 dict 注册方式一致。"""
    def decorator(fn: CheckerFunc) -> CheckerFunc:
        CHECKER_REGISTRY[checker_id] = fn
        return fn
    return decorator


# ============================================================
# 内置 Checker 实现
# ============================================================

@register_checker("file.exists")
def checker_file_exists(target: dict, expected: Any, context: dict) -> CheckerResult:
    """检查指定文件是否存在。

    target.kind = "filesystem"
    target.path = 相对路径
    expected = bool （True=必须存在, False=必须不存在）
    """
    path = target.get("path", "")
    if not path:
        return CheckerResult(False, "target.path 为空")

    import os
    meta = context.get("meta", {})
    workspace_path = meta.get("workspace_path", "")
    full_path = os.path.join(workspace_path, path) if workspace_path else path

    exists = os.path.exists(full_path)
    if expected is True and not exists:
        return CheckerResult(False, f"文件不存在: {path}",
                             {"full_path": full_path, "expected_exists": True})
    if expected is False and exists:
        return CheckerResult(False, f"文件不应存在但对已存在: {path}",
                             {"full_path": full_path, "expected_exists": False})
    return CheckerResult(True, f"文件检查通过: {path}",
                         {"full_path": full_path, "exists": exists})


@register_checker("artifact.created")
def checker_artifact_created(target: dict, expected: Any, context: dict) -> CheckerResult:
    """检查产物事件中是否包含指定的 artifact。

    target.kind = "artifact"
    target.artifact_type = 产物类型
    expected = min_count (int)
    """
    artifact_type = target.get("artifact_type", "")
    min_count = int(expected) if isinstance(expected, (int, float)) else 1
    if min_count < 1:
        min_count = 1

    events = context.get("events", [])
    if not isinstance(events, list):
        events = []

    matched = 0
    for evt in events:
        if not isinstance(evt, dict):
            continue
        evt_type = evt.get("type", "")
        payload = evt.get("payload", {})
        if isinstance(payload, dict):
            if evt_type == "artifact_created" and payload.get("artifact_type") == artifact_type:
                matched += 1
            elif evt_type == artifact_type:
                matched += 1

    if matched >= min_count:
        return CheckerResult(True, f"产物 '{artifact_type}' 已创建 (count={matched})",
                             {"matched": matched, "min_count": min_count})
    return CheckerResult(False, f"产物 '{artifact_type}' 不足: {matched}/{min_count}",
                         {"matched": matched, "min_count": min_count})


@register_checker("plan.artifacts_match")
def checker_plan_artifacts_match(target: dict, expected: Any, context: dict) -> CheckerResult:
    """检查 plan 声明的产物与实际创建产物的匹配度。

    target.kind = "plan_artifacts"
    expected 未使用（由 plan 自身提供期望值）
    """
    meta = context.get("meta", {})
    plan_artifacts = meta.get("plan_artifacts", {})
    expected_files = plan_artifacts.get("expected_files", [])

    if not expected_files:
        return CheckerResult(True, "plan 未声明预期文件，跳过产物匹配检查")

    events = context.get("events", [])
    if not isinstance(events, list):
        events = []

    created_files: set = set()
    for evt in events:
        if not isinstance(evt, dict):
            continue
        payload = evt.get("payload", {})
        if isinstance(payload, dict):
            path = payload.get("path", "") or payload.get("file", "")
            if path:
                created_files.add(path)

    matched = set(expected_files) & created_files
    ratio = len(matched) / len(expected_files) if expected_files else 1.0

    if ratio >= 0.5:
        return CheckerResult(True, f"产物匹配: {len(matched)}/{len(expected_files)} (ratio={ratio:.0%})",
                             {"matched": list(matched), "expected": expected_files, "ratio": ratio})
    return CheckerResult(False, f"产物匹配不足: {len(matched)}/{len(expected_files)} (ratio={ratio:.0%})",
                         {"matched": list(matched), "expected": expected_files, "ratio": ratio})


@register_checker("step.completed")
def checker_step_completed(target: dict, expected: Any, context: dict) -> CheckerResult:
    """检查指定步骤是否成功完成。

    target.kind = "step"
    target.step_id = 步骤 ID
    expected = None（仅检查 completion）
    """
    step_id = target.get("step_id", "")
    if not step_id:
        return CheckerResult(False, "target.step_id 为空")

    intermediate = context.get("intermediate_results", [])
    if not isinstance(intermediate, list):
        intermediate = []

    for item in intermediate:
        if not isinstance(item, dict):
            continue
        if item.get("type") == step_id or item.get("step_id") == step_id:
            if item.get("llm_success") is False:
                return CheckerResult(False, f"步骤 '{step_id}' 执行失败")
            if item.get("status") == "failed":
                return CheckerResult(False, f"步骤 '{step_id}' 状态为 failed")
            return CheckerResult(True, f"步骤 '{step_id}' 已完成")

    return CheckerResult(False, f"步骤 '{step_id}' 未找到执行记录")


@register_checker("test.passed")
def checker_test_passed(target: dict, expected: Any, context: dict) -> CheckerResult:
    """检查测试步骤是否通过。

    target.kind = "test_result"
    expected = min_pass_count (int, 默认 1)
    """
    min_pass = int(expected) if isinstance(expected, (int, float)) else 1
    if min_pass < 1:
        min_pass = 1

    intermediate = context.get("intermediate_results", [])
    if not isinstance(intermediate, list):
        intermediate = []

    for item in reversed(intermediate):
        if not isinstance(item, dict):
            continue
        if item.get("type") != "test":
            continue
        test_output = item.get("output", item.get("test_result", {}))
        if isinstance(test_output, dict):
            passed = test_output.get("passed", 0)
            if isinstance(passed, (int, float)) and passed >= min_pass:
                return CheckerResult(True, f"测试通过: {passed} >= {min_pass}",
                                     {"passed": passed, "min_pass": min_pass})
        elif isinstance(test_output, str):
            if "FAILED" not in test_output.upper() and "error" not in test_output.lower():
                return CheckerResult(True, "测试输出未包含失败标记",
                                     {"output_snippet": test_output[:200]})
        return CheckerResult(False, "测试未通过", {"output_snippet": str(test_output)[:200]})

    return CheckerResult(False, "未找到测试步骤结果")


# ============================================================
# Checker 执行入口
# ============================================================

def run_checker(
    checker_id: str,
    target: Dict[str, Any],
    expected: Any,
    context: Dict[str, Any],
) -> CheckerResult:
    """执行已注册的 checker。

    PT-05: checker 未注册 → 返回失败结果（不抛异常）。
    PT-06: checker 运行失败 → 返回失败结果并记录证据。
    """
    if checker_id not in CHECKER_REGISTRY:
        return CheckerResult(
            False,
            f"checker '{checker_id}' 未注册",
            {"registered_checkers": list(CHECKER_REGISTRY.keys())}
        )

    try:
        handler = CHECKER_REGISTRY[checker_id]
        result = handler(target, expected, context)
        if not isinstance(result, CheckerResult):
            return CheckerResult(
                False,
                f"checker '{checker_id}' 返回了非 CheckerResult 类型: {type(result).__name__}"
            )
        return result
    except Exception as e:
        return CheckerResult(
            False,
            f"checker '{checker_id}' 执行异常: {type(e).__name__}: {e}",
            {"exception_type": type(e).__name__, "exception_message": str(e)}
        )


# ============================================================
# 组合验证
# ============================================================

def run_validation_conditions(
    conditions: List[Dict[str, Any]],
    context: Dict[str, Any],
    block_on_failure: bool = True,
) -> Tuple[bool, List[CheckerResult]]:
    """批量执行验证条件。

    Args:
        conditions: 验证条件列表（PC-04 格式）
        context: 执行上下文
        block_on_failure: True = 只要有必需条件失败就立即阻断

    Returns:
        (all_passed, results)
    """
    results: List[CheckerResult] = []

    for cond in conditions:
        if not isinstance(cond, dict):
            continue

        checker_id = cond.get("checker", "")
        target = cond.get("target", {})
        expected = cond.get("expected")
        required = cond.get("required", True)
        on_failure = cond.get("on_failure", "block_completion")

        result = run_checker(checker_id, target, expected, context)
        results.append(result)

        if not result.passed and required and on_failure == "block_completion":
            if block_on_failure:
                return False, results

    all_passed = all(
        r.passed for i, r in enumerate(results)
        if conditions[i].get("required", True)
    )
    return all_passed, results


def get_registered_checkers() -> List[str]:
    """返回已注册的 checker ID 列表。"""
    return list(CHECKER_REGISTRY.keys())