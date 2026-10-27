# -*- coding: utf-8 -*-
# intent_router/_planning_contract.py
# ---------------------------------------------------------
# Planning Contract v1.0 — 最小实现
# 不新增 Agent、不改变现有调度机制、不引入旁路端点
# ---------------------------------------------------------

from typing import Dict, List, Optional, Set, Tuple

# =========================================================
# 1. implementation_plan_requirement 映射
#    由受信任策略（非 LLM）决定，LLM 不得降级
# =========================================================

IMPL_PLAN_REQUIREMENT: Dict[str, str] = {
    # not_applicable: 纯对话/只读解释，无需代码实施方案
    "chat":             "not_applicable",
    "mentor_explain":   "not_applicable",
    "explain_code":     "not_applicable",
    "code_review":      "not_applicable",

    # optional: 需要分析但可跳过实施方案（如生成文档/架构设计）
    "analysis":         "optional",
    "architecture":     "optional",
    "generate_doc":     "optional",
    "set_preference":   "optional",
    "creative_writing": "optional",

    # required: 必须先生成实施方案再写入代码
    "write_code":       "required",
    "fix_code":         "required",
    "explain_and_fix":  "required",
    "refactor":         "required",
    "delete_files":     "required",
    "workspace_maintenance": "required",
    "vision_analysis":  "required",
    "external_git":     "required",
}

# =========================================================
# 2. 重规划策略表 — 允许的 intent 重定向
#    Post-analyze 重路由前必须通过此策略检查
# =========================================================

# 安全转换: 同一能力域内，仅增加步骤
SAFE_REDIRECTIONS: Dict[str, Set[str]] = {
    "fix_code":         {"write_code", "explain_and_fix"},
    "write_code":       {"fix_code", "refactor"},
    "explain_and_fix":  {"fix_code", "write_code"},
    "refactor":         {"write_code"},
    "architecture":     {"write_code", "refactor"},  # 架构设计后可进入实现
    "analysis":         {"write_code", "fix_code", "architecture", "refactor"},
}

# 禁止转换: 跨能力域、能力升级、权限扩大
BLOCKED_REDIRECTIONS: Set[Tuple[str, str]] = {
    # 对话/只读 → 写入（权限升级）
    ("chat",            "write_code"),
    ("chat",            "fix_code"),
    ("chat",            "delete_files"),
    ("chat",            "external_git"),
    ("mentor_explain",  "write_code"),
    ("mentor_explain",  "fix_code"),
    ("mentor_explain",  "delete_files"),
    ("code_review",     "write_code"),
    ("code_review",     "fix_code"),
    ("code_review",     "delete_files"),
    ("explain_code",    "write_code"),
    ("explain_code",    "fix_code"),

    # 代码 → 删除（新增删除能力）
    ("write_code",      "delete_files"),
    ("fix_code",        "delete_files"),

    # 任意 → Git（新增外部操作）
    ("write_code",      "external_git"),
    ("fix_code",        "external_git"),
    ("architecture",    "external_git"),
    ("refactor",        "external_git"),

    # 任意 → 工作区维护（新增环境操作）
    ("write_code",      "workspace_maintenance"),
    ("fix_code",        "workspace_maintenance"),
}


def get_impl_plan_requirement(intent: str) -> str:
    """返回指定意图的 implementation_plan_requirement"""
    return IMPL_PLAN_REQUIREMENT.get(intent, "required")


def validate_replan(
    old_intent: str,
    new_intent: str,
) -> Tuple[bool, Optional[str]]:
    """校验重规划是否被策略允许。

    Returns:
        (allowed, reason)
        - allowed=True: 允许重定向
        - allowed=False: 拒绝，reason 说明原因
        - reason=None 表示未触发任何规则（允许，走默认路径）
    """
    if old_intent == new_intent:
        return True, None

    check_pair = (old_intent, new_intent)

    # 1) 禁止列表检查
    if check_pair in BLOCKED_REDIRECTIONS:
        return False, f"BLOCKED: {old_intent} → {new_intent} 跨能力域或权限升级"

    # 2) 安全列表检查
    if old_intent in SAFE_REDIRECTIONS and new_intent in SAFE_REDIRECTIONS[old_intent]:
        return True, None

    # 3) 未在安全列表中 → 默认允许但标记"需审核"
    #    保留 v4.0 动态决策能力，不硬阻断
    return True, f"REVIEW: {old_intent} → {new_intent} 不在已知安全列表中，需监控"


def needs_reauthorization(old_intent: str, new_intent: str) -> bool:
    """检查重规划是否需要重新授权。

    当重规划新增写入、删除、外部访问或改变精确操作对象时需重授权。
    """
    _write_intents = {"write_code", "fix_code", "refactor", "explain_and_fix",
                      "delete_files", "workspace_maintenance"}
    _read_only = {"chat", "mentor_explain", "explain_code", "code_review",
                  "analysis", "creative_writing"}

    # 只读 → 写入
    if old_intent in _read_only and new_intent in _write_intents:
        return True

    # 任意 → 删除
    if new_intent == "delete_files":
        return True

    # 任意 → Git
    if new_intent == "external_git":
        return True

    return False