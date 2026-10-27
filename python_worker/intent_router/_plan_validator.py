# -*- coding: utf-8 -*-
# intent_router/_plan_validator.py
# ---------------------------------------------------------
# Planning Contract v1.0 — 计划校验引擎
# PT-01 / PT-02 / PT-03: 字段校验、步骤依赖校验、前置条件检查
# 纯函数模块，不修改生产代码路径，不引入新 Agent
# ---------------------------------------------------------

from typing import Dict, List, Set, Optional, Any, Tuple


# ============================================================
# Step 类型白名单（与 STEP_DISPATCHER 对齐）
# ============================================================
VALID_STEP_TYPES: Set[str] = {
    "vision_analysis",
    "analyze",
    "plan",
    "write",
    "refine",
    "test",
    "fix",
    "profile",
    "doc",
    "docstring",
    "respond",
    "workspace",
}

# ============================================================
# Plan 必需字段
# ============================================================
REQUIRED_PLAN_FIELDS = [
    "intent",
    "execution_chain",
]

REQUIRED_STEP_FIELDS = [
    "id",
    "type",
    "input",
]


class PlanValidationError(Exception):
    """计划校验失败（PT-01 / PT-02）。"""
    pass


class PlanValidationResult:
    """计划校验结果。"""

    __slots__ = ("valid", "errors", "warnings")

    def __init__(self):
        self.valid = True
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def add_error(self, msg: str):
        self.errors.append(msg)
        self.valid = False

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    def raise_if_invalid(self):
        if not self.valid:
            raise PlanValidationError(
                f"计划校验失败 ({len(self.errors)} 错误):\n" +
                "\n".join(f"  - {e}" for e in self.errors)
            )

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


# ============================================================
# 1. 字段校验（PT-01）
# ============================================================

def validate_plan_fields(plan: dict) -> PlanValidationResult:
    """校验 plan 对象的必需字段和字段类型。

    PT-01: 缺少必需字段或字段类型错误 → 激活前拒绝计划。
    """
    result = PlanValidationResult()

    if not isinstance(plan, dict):
        result.add_error(f"plan 必须是 dict, 实际 {type(plan).__name__}")
        return result

    # 必需字段存在性
    for field in REQUIRED_PLAN_FIELDS:
        if field not in plan:
            result.add_error(f"缺少必需字段: plan.{field}")

    # intent 类型
    if "intent" in plan:
        if not isinstance(plan["intent"], str) or not plan["intent"].strip():
            result.add_error("plan.intent 必须是非空字符串")

    # execution_chain 类型
    if "execution_chain" in plan:
        chain = plan["execution_chain"]
        if not isinstance(chain, list):
            result.add_error(f"plan.execution_chain 必须是 list, 实际 {type(chain).__name__}")
        else:
            for i, step_type in enumerate(chain):
                if not isinstance(step_type, str) or not step_type.strip():
                    result.add_error(f"plan.execution_chain[{i}] 必须是非空字符串")
                elif step_type not in VALID_STEP_TYPES:
                    result.add_warning(
                        f"plan.execution_chain[{i}] 步骤类型 '{step_type}' 不在已知白名单中"
                    )

    # implementation_plan_requirement 校验
    if "implementation_plan_requirement" in plan:
        req = plan["implementation_plan_requirement"]
        if req not in ("required", "optional", "not_applicable"):
            result.add_error(
                f"plan.implementation_plan_requirement 必须为 required|optional|not_applicable, "
                f"实际 '{req}'"
            )

    # person 类型检查（可选字段）
    if "persona" in plan:
        if not isinstance(plan["persona"], str) or not plan["persona"].strip():
            result.add_warning("plan.persona 应是有效字符串")

    # 检查 execution_plan 完整对象（plan_request 输出）
    _validate_full_execution_plan(plan, result)

    return result


def _validate_full_execution_plan(plan: dict, result: PlanValidationResult):
    """对 IntentRouter.plan_request() 完整输出的附加校验。"""
    extra_fields = {
        "mode": str,
        "context_requirements": list,
        "capabilities": list,
        "side_effects": list,
        "approval": dict,
        "validation": list,
        "recovery": list,
    }

    for field, expected_type in extra_fields.items():
        if field in plan:
            value = plan[field]
            if not isinstance(value, expected_type):
                result.add_warning(
                    f"plan.{field} 类型期望 {expected_type.__name__}, "
                    f"实际 {type(value).__name__}"
                )


# ============================================================
# 2. 步骤结构校验（PT-02）
# ============================================================

def validate_steps(steps: List[dict]) -> PlanValidationResult:
    """校验步骤列表：ID 唯一性、依赖引用有效性、步骤类型白名单。

    PT-02: step_id 重复、依赖不存在或依赖图有环 → 校验失败。
    """
    result = PlanValidationResult()

    if not isinstance(steps, list):
        result.add_error(f"steps 必须是 list, 实际 {type(steps).__name__}")
        return result

    if not steps:
        result.add_error("steps 列表为空")
        return result

    # 收集所有 step id
    step_ids: Set[str] = set()
    id_to_step: Dict[str, dict] = {}

    for i, step in enumerate(steps):
        # 类型检查
        if not isinstance(step, dict):
            result.add_error(f"steps[{i}] 必须是 dict, 实际 {type(step).__name__}")
            continue

        # 必需字段
        for field in REQUIRED_STEP_FIELDS:
            if field not in step:
                result.add_error(f"steps[{i}] 缺少必需字段: '{field}'")

        # ID 唯一性
        sid = step.get("id", "")
        if sid:
            if sid in step_ids:
                result.add_error(f"step_id 重复: '{sid}' (出现于索引 {i} 和之前)")
            step_ids.add(sid)
            id_to_step[sid] = step

        # 类型白名单
        stype = step.get("type", "")
        if stype and stype not in VALID_STEP_TYPES:
            result.add_error(
                f"steps[{i}] type '{stype}' 不在已知白名单中"
            )

    if not result.valid:
        return result

    return result


def validate_dependencies(steps: List[dict]) -> PlanValidationResult:
    """校验步骤依赖：引用有效性 + 无环。

    PT-02: 依赖不存在或依赖图有环 → 校验失败。
    """
    result = PlanValidationResult()

    if not isinstance(steps, list):
        result.add_error(f"steps 必须是 list, 实际 {type(steps).__name__}")
        return result

    id_to_step: Dict[str, dict] = {}
    for step in steps:
        sid = step.get("id", "")
        if sid:
            id_to_step[sid] = step

    # 收集所有依赖关系
    step_ids = set(id_to_step.keys())
    deps: Dict[str, List[str]] = {}  # step_id → [dep_ids]

    for step in steps:
        sid = step.get("id", "")
        dep_list = step.get("depends_on", [])
        if not isinstance(dep_list, list):
            result.add_error(
                f"steps[{sid}] depends_on 必须是 list, "
                f"实际 {type(dep_list).__name__}"
            )
            continue
        deps[sid] = dep_list

        for dep_id in dep_list:
            if not isinstance(dep_id, str):
                result.add_error(
                    f"steps[{sid}] depends_on 中包含非字符串依赖: {dep_id!r}"
                )
                continue
            if dep_id not in step_ids:
                result.add_error(
                    f"steps[{sid}] 依赖不存在的步骤: '{dep_id}'"
                )

    if not result.valid:
        return result

    # 检测环
    cycles = _find_dependency_cycles(step_ids, deps)
    if cycles:
        for cycle in cycles:
            result.add_error(
                f"依赖图存在环: {' → '.join(cycle)} → {cycle[0]}"
            )

    return result


def _find_dependency_cycles(
    nodes: Set[str],
    deps: Dict[str, List[str]],
) -> List[List[str]]:
    """DFS 查找依赖图中的所有环。"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}
    parent: Dict[str, Optional[str]] = {}
    cycles: List[List[str]] = []

    def dfs(u: str):
        color[u] = GRAY
        for v in deps.get(u, []):
            if v not in nodes:
                continue
            if color[v] == GRAY:
                # 找到环：回溯 parent 链
                cycle = [v]
                cur = u
                while cur != v and cur is not None:
                    cycle.append(cur)
                    cur = parent.get(cur)
                cycle.append(v)
                cycle.reverse()
                cycles.append(cycle)
            elif color[v] == WHITE:
                parent[v] = u
                dfs(v)
        color[u] = BLACK

    for n in nodes:
        if color[n] == WHITE:
            dfs(n)

    return cycles


# ============================================================
# 3. 前置条件检查（PT-03）
# ============================================================

def check_preconditions(
    step: dict,
    completed_step_ids: Set[str],
    step_results: Dict[str, dict],
) -> PlanValidationResult:
    """检查步骤的依赖是否全部成功完成。

    PT-03: 前置步骤未成功完成 → 阻断依赖步骤启动。
    """
    result = PlanValidationResult()

    sid = step.get("id", "?")
    deps = step.get("depends_on", [])
    if not isinstance(deps, list):
        deps = []

    for dep_id in deps:
        if dep_id not in completed_step_ids:
            result.add_error(
                f"步骤 '{sid}' 的依赖 '{dep_id}' 尚未完成"
            )
            continue

        # 检查依赖步骤是否成功
        dep_result = step_results.get(dep_id, {})
        dep_status = dep_result.get("status", "")
        dep_success = dep_result.get("success", None)

        if dep_status == "FAILED" or dep_success is False:
            result.add_error(
                f"步骤 '{sid}' 的依赖 '{dep_id}' 执行失败"
            )

    return result


# ============================================================
# 4. 计划完整性校验（组合校验）
# ============================================================

def validate_plan_full(
    plan: dict,
    steps: Optional[List[dict]] = None,
    min_chain_length: int = 1,
) -> PlanValidationResult:
    """组合校验：plan 字段 + steps 结构 + 依赖。

    返回 PlanValidationResult，调用方决定如何处理。
    """
    result = validate_plan_fields(plan)

    if steps is not None:
        step_result = validate_steps(steps)
        for e in step_result.errors:
            result.add_error(e)
        for w in step_result.warnings:
            result.add_warning(w)

        if step_result.valid:
            dep_result = validate_dependencies(steps)
            for e in dep_result.errors:
                result.add_error(e)
            for w in dep_result.warnings:
                result.add_warning(w)

    # 链长度检查
    chain = plan.get("execution_chain", [])
    if isinstance(chain, list) and len(chain) < min_chain_length:
        result.add_error(
            f"execution_chain 长度 {len(chain)} < {min_chain_length}"
        )

    return result