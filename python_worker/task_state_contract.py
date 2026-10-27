# -*- coding: utf-8 -*-
"""
G1.1 v0.2 任务状态契约

纯定义模块，不修改生产代码。定义：
- TaskState: 任务生命周期（5 个状态 + 合法转换表）
- StepState:  步骤执行情况（6 个状态）
- ExecutionResult: 与 TaskState 的分离约定
- AuditEvent:  审计事件类型 + 幂等键规则
- Legacy Mapping: task_state 与旧 status 字段的双向映射
"""

import os
from typing import Dict, Any, Optional, List, Tuple, Set

# ================================================================
# 1. TaskState — 任务生命周期
# ================================================================

TASK_STATE_PENDING                 = "PENDING"
TASK_STATE_RUNNING                 = "RUNNING"
TASK_STATE_WAITING_AUTHORIZATION   = "WAITING_AUTHORIZATION"
TASK_STATE_COMPLETED               = "COMPLETED"
TASK_STATE_FAILED                  = "FAILED"

TASK_STATES_ALL: Set[str] = {
    TASK_STATE_PENDING,
    TASK_STATE_RUNNING,
    TASK_STATE_WAITING_AUTHORIZATION,
    TASK_STATE_COMPLETED,
    TASK_STATE_FAILED,
}

TASK_STATES_TERMINAL: Set[str] = {
    TASK_STATE_COMPLETED,
    TASK_STATE_FAILED,
}

# 合法转换表：{ (from, to): True }
# from = None 表示初始状态（任务刚被创建）
LEGAL_TRANSITIONS: Dict[Tuple[Optional[str], str], bool] = {
    # PENDING → *
    (None,                  TASK_STATE_PENDING):                 True,
    (TASK_STATE_PENDING,    TASK_STATE_RUNNING):                 True,
    (TASK_STATE_PENDING,    TASK_STATE_FAILED):                  True,

    # RUNNING → *
    (TASK_STATE_RUNNING,    TASK_STATE_WAITING_AUTHORIZATION):   True,
    (TASK_STATE_RUNNING,    TASK_STATE_COMPLETED):               True,
    (TASK_STATE_RUNNING,    TASK_STATE_FAILED):                  True,

    # WAITING_AUTHORIZATION → *
    (TASK_STATE_WAITING_AUTHORIZATION, TASK_STATE_COMPLETED):    True,
    (TASK_STATE_WAITING_AUTHORIZATION, TASK_STATE_FAILED):       True,
}

# 禁止转换（对应 None 的 False 值，用于显式测试）
ILLEGAL_TRANSITIONS: List[Tuple[Optional[str], str]] = [
    (None,                  TASK_STATE_RUNNING),
    (None,                  TASK_STATE_COMPLETED),
    (None,                  TASK_STATE_FAILED),
    (TASK_STATE_PENDING,    TASK_STATE_COMPLETED),
    (TASK_STATE_PENDING,    TASK_STATE_WAITING_AUTHORIZATION),
    (TASK_STATE_RUNNING,    TASK_STATE_PENDING),
    (TASK_STATE_COMPLETED,  TASK_STATE_RUNNING),
    (TASK_STATE_COMPLETED,  TASK_STATE_FAILED),
    (TASK_STATE_COMPLETED,  TASK_STATE_COMPLETED),
    (TASK_STATE_FAILED,     TASK_STATE_RUNNING),
    (TASK_STATE_FAILED,     TASK_STATE_COMPLETED),
    (TASK_STATE_FAILED,     TASK_STATE_FAILED),
    (TASK_STATE_WAITING_AUTHORIZATION, TASK_STATE_RUNNING),
    (TASK_STATE_WAITING_AUTHORIZATION, TASK_STATE_PENDING),
]


def transition_is_legal(
    from_state: Optional[str],
    to_state: str,
) -> bool:
    return (from_state, to_state) in LEGAL_TRANSITIONS


# ================================================================
# 2. StepState — 步骤执行情况
# ================================================================

STEP_STATE_PENDING               = "pending"
STEP_STATE_RUNNING               = "running"
STEP_STATE_COMPLETED             = "completed"
STEP_STATE_FAILED                = "failed"
STEP_STATE_AWAITING_AUTHORIZATION = "awaiting_authorization"
STEP_STATE_SKIPPED               = "skipped"

STEP_STATES_ALL: Set[str] = {
    STEP_STATE_PENDING,
    STEP_STATE_RUNNING,
    STEP_STATE_COMPLETED,
    STEP_STATE_FAILED,
    STEP_STATE_AWAITING_AUTHORIZATION,
    STEP_STATE_SKIPPED,
}

# 步骤状态与任务状态的相容性
# 如果任务处于某个 TaskState，步骤可以是什么 StepState
STEP_STATE_COMPATIBILITY: Dict[str, Set[str]] = {
    TASK_STATE_PENDING:                 {STEP_STATE_PENDING},
    TASK_STATE_RUNNING:                 {STEP_STATE_PENDING, STEP_STATE_RUNNING,
                                         STEP_STATE_COMPLETED, STEP_STATE_FAILED,
                                         STEP_STATE_AWAITING_AUTHORIZATION,
                                         STEP_STATE_SKIPPED},
    TASK_STATE_WAITING_AUTHORIZATION:   {STEP_STATE_COMPLETED, STEP_STATE_AWAITING_AUTHORIZATION,
                                         STEP_STATE_FAILED, STEP_STATE_SKIPPED},
    TASK_STATE_COMPLETED:               {STEP_STATE_COMPLETED, STEP_STATE_SKIPPED, STEP_STATE_FAILED},
    TASK_STATE_FAILED:                  {STEP_STATE_COMPLETED, STEP_STATE_FAILED,
                                         STEP_STATE_SKIPPED, STEP_STATE_PENDING},
}


# ================================================================
# 3. ExecutionResult — 执行结果
# ================================================================

# task_state → 旧 status 字段的单向映射
TASK_STATE_TO_LEGACY_STATUS: Dict[str, str] = {
    TASK_STATE_PENDING:                 "pending",
    TASK_STATE_RUNNING:                 "pending",
    TASK_STATE_WAITING_AUTHORIZATION:   "awaiting_authorization",
    TASK_STATE_COMPLETED:               "done",
    TASK_STATE_FAILED:                  "error",
}

# 旧 status → task_state 的逆向映射（仅终态可逆）
LEGACY_STATUS_TO_TASK_STATE: Dict[str, str] = {
    "pending":                  TASK_STATE_PENDING,    # 宽松映射（也可能是 RUNNING）
    "awaiting_authorization":   TASK_STATE_WAITING_AUTHORIZATION,
    "done":                     TASK_STATE_COMPLETED,
    "error":                    TASK_STATE_FAILED,
}


# ================================================================
# 4. AuditEvent — 审计事件
# ================================================================

AUDIT_EVENT_TASK_CREATED               = "task_created"
AUDIT_EVENT_TASK_STARTED               = "task_started"
AUDIT_EVENT_TASK_COMPLETED             = "task_completed"
AUDIT_EVENT_TASK_FAILED                = "task_failed"
AUDIT_EVENT_TASK_AWAITING_AUTHORIZATION = "task_awaiting_authorization"
AUDIT_EVENT_CHAIN_REBUILT              = "chain_rebuilt"
AUDIT_EVENT_STEP_STARTED               = "step_started"
AUDIT_EVENT_STEP_COMPLETED             = "step_completed"
AUDIT_EVENT_STEP_FAILED                = "step_failed"
AUDIT_EVENT_STEP_SKIPPED               = "step_skipped"

# 每种 TaskState 路径对应的事件类型序列（合法事件集合，非唯一顺序）
# key = 目标 TaskState, value = 允许出现的事件集合
TASK_STATE_EVENT_SETS: Dict[str, Set[str]] = {
    TASK_STATE_FAILED: {
        AUDIT_EVENT_TASK_STARTED, AUDIT_EVENT_TASK_FAILED,
        AUDIT_EVENT_STEP_STARTED, AUDIT_EVENT_STEP_COMPLETED,
        AUDIT_EVENT_STEP_FAILED, AUDIT_EVENT_STEP_SKIPPED,
    },
    TASK_STATE_COMPLETED: {
        AUDIT_EVENT_TASK_STARTED, AUDIT_EVENT_TASK_COMPLETED,
        AUDIT_EVENT_STEP_STARTED, AUDIT_EVENT_STEP_COMPLETED,
        AUDIT_EVENT_STEP_SKIPPED,
    },
    TASK_STATE_WAITING_AUTHORIZATION: {
        AUDIT_EVENT_TASK_STARTED, AUDIT_EVENT_TASK_AWAITING_AUTHORIZATION,
        AUDIT_EVENT_STEP_STARTED, AUDIT_EVENT_STEP_COMPLETED,
        AUDIT_EVENT_STEP_FAILED, AUDIT_EVENT_STEP_SKIPPED,
    },
    TASK_STATE_RUNNING: {
        AUDIT_EVENT_TASK_STARTED,
        AUDIT_EVENT_STEP_STARTED, AUDIT_EVENT_STEP_COMPLETED,
        AUDIT_EVENT_STEP_FAILED, AUDIT_EVENT_STEP_SKIPPED,
    },
}

# 不允许出现的事件组合
FORBIDDEN_EVENT_PAIRS: List[Tuple[str, str]] = [
    (AUDIT_EVENT_TASK_COMPLETED, AUDIT_EVENT_TASK_FAILED),
    (AUDIT_EVENT_TASK_COMPLETED, AUDIT_EVENT_TASK_AWAITING_AUTHORIZATION),
    (AUDIT_EVENT_TASK_FAILED, AUDIT_EVENT_TASK_COMPLETED),
]

# 幂等键格式: task_id:event_type:sequence
EVENT_IDEMPOTENCY_KEY_FORMAT = "{task_id}:{event_type}:{sequence}"


def build_event_idempotency_key(
    task_id: str, event_type: str, sequence: int
) -> str:
    return EVENT_IDEMPOTENCY_KEY_FORMAT.format(
        task_id=task_id, event_type=event_type, sequence=sequence
    )


# ================================================================
# 5. 错误码
# ================================================================

ERROR_CODE_TASK_CANCELLED      = "TASK_CANCELLED"
ERROR_CODE_TASK_PROTOCOL_ERROR = "TASK_PROTOCOL_ERROR"
ERROR_CODE_MODEL_CALL_ERROR    = "MODEL_CALL_ERROR"
ERROR_CODE_CONTRACT_VIOLATION  = "CONTRACT_VIOLATION"
ERROR_CODE_STEP_EXECUTION_ERROR = "STEP_EXECUTION_ERROR"
ERROR_CODE_UNKNOWN_ERROR           = "UNKNOWN_ERROR"
ERROR_CODE_EVIDENCE_GATE_BLOCKED   = "EVIDENCE_GATE_BLOCKED"

# 合法旧 status 值（用于反向兼容校验）
VALID_LEGACY_STATUS_VALUES: Set[str] = {"done", "error", "pending", "awaiting_authorization"}


# ================================================================
# 6. 状态守卫：防止终止状态下继续执行步骤
# ================================================================

def guard_not_terminal_state(
    current_state: Optional[str],
    task_id: str = "",
    caller: str = "",
) -> bool:
    """如果任务已处于终止状态 (COMPLETED/FAILED)，返回 False 以阻止步骤执行。
    
    返回 True → 安全，可以继续执行步骤。
    返回 False → 任务已终止，应跳过步骤执行且不追加 step_finished。
    """
    if current_state in TASK_STATES_TERMINAL:
        label = f"[StateGuard]{' ' + caller if caller else ''}"
        print(f"{label} 任务 {task_id} 已处于终止状态 ({current_state})，跳过步骤执行")
        return False
    return True


# ================================================================
# 7. 契约验证函数
# ================================================================

class ContractViolation:
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message

    def __repr__(self):
        return f"ContractViolation(field={self.field!r}, message={self.message!r})"



class ContractViolationError(Exception):
    pass


class EvidenceGateBlocked(Exception):
    """输出准入阻断：缺少必需的工作区证据，不允许生成项目事实型结论。"""
    def __init__(self, reason: str = "工作区证据缺失"):
        self.reason = reason
        super().__init__(f"EvidenceGate blocked: {reason}")


def validate_result_contract(result: Dict[str, Any]) -> List[ContractViolation]:
    """
    验证一个结果对象是否符合 G1.1 契约。
    返回违规列表，空列表 = 符合契约。

    注意：本函数对 task_state 和 status 做 trim 处理（去除首尾空白）。
    """
    violations: List[ContractViolation] = []

    # 预处理：trim 字段值
    raw_task_state = result.get("task_state")
    raw_status = result.get("status")
    task_state = raw_task_state.strip() if isinstance(raw_task_state, str) and raw_task_state.strip() != "" else None
    status_val = raw_status.strip() if isinstance(raw_status, str) and raw_status.strip() != "" else None

    # A. 字段存在性
    if task_state is None:
        if status_val is None:
            violations.append(ContractViolation(
                "task_state|status",
                "两个字段均缺失，不得默认 done 或 pending"
            ))
        elif status_val not in VALID_LEGACY_STATUS_VALUES:
            violations.append(ContractViolation(
                "status",
                f"task_state 缺失时，未知 status 值 {status_val!r}，"
                f"合法值: {VALID_LEGACY_STATUS_VALUES}"
            ))
    else:
        if task_state not in TASK_STATES_ALL:
            violations.append(ContractViolation(
                "task_state",
                f"非法值 {task_state!r}，合法值: {TASK_STATES_ALL}"
            ))

    # B. 旧字段一致性（仅当 task_state 有效时检查）
    if task_state is not None and task_state in TASK_STATES_ALL:
        if status_val is not None:
            expected_legacy = TASK_STATE_TO_LEGACY_STATUS.get(task_state)
            if status_val != expected_legacy:
                # 兼容别名：COMPLETED + 'completed' → 接受
                if task_state == TASK_STATE_COMPLETED and status_val == "completed":
                    pass  # compatibility alias, no violation
                else:
                    violations.append(ContractViolation(
                        "status",
                        f"task_state={task_state!r} 要求 status={expected_legacy!r}，"
                        f"实际 status={status_val!r}"
                    ))

    # C. 终态判定
    if task_state is not None and task_state in TASK_STATES_TERMINAL:
        meta = result.get("meta", {})
        if meta.get("finished_at") is None:
            violations.append(ContractViolation(
                "meta.finished_at",
                f"终态 task_state={task_state!r} 要求 finished_at 非空"
            ))

    # D. 步骤状态相容性
    # 步骤可能位于 result["result"]["steps"]（新结构）或 result["steps"]（兼容位置）
    if isinstance(result.get("result"), dict):
        steps = result["result"].get("steps", [])
    else:
        steps = result.get("steps") or []

    if task_state is not None and task_state in STEP_STATE_COMPATIBILITY:
        allowed_step_states = STEP_STATE_COMPATIBILITY[task_state]
        for i, step in enumerate(steps):
            step_status = step.get("status")
            if step_status and step_status not in STEP_STATES_ALL:
                violations.append(ContractViolation(
                    f"steps[{i}].status",
                    f"非法步骤状态 {step_status!r}，合法值: {STEP_STATES_ALL}"
                ))
            elif step_status and step_status not in allowed_step_states:
                violations.append(ContractViolation(
                    f"steps[{i}].status",
                    f"步骤状态 {step_status!r} 与任务状态 {task_state!r} 不相容"
                ))

            # 终态不能有 running 步骤
            if task_state in TASK_STATES_TERMINAL and step_status == STEP_STATE_RUNNING:
                violations.append(ContractViolation(
                    f"steps[{i}].status",
                    f"终态任务 {task_state!r} 不能包含 running 步骤"
                ))

    # E. skipped 步骤必须有 reason
    for i, step in enumerate(steps):
        if step.get("status") == STEP_STATE_SKIPPED:
            if not step.get("reason"):
                violations.append(ContractViolation(
                    f"steps[{i}].reason",
                    "skipped 步骤必须有非空 reason"
                ))

    # F. 事件合法性
    events = result.get("events") or []
    task_state = result.get("task_state")
    if task_state and task_state in TASK_STATE_EVENT_SETS:
        allowed_events = TASK_STATE_EVENT_SETS[task_state]
        event_types = {e.get("event") for e in events if e.get("event")}
        for illegal_pair in FORBIDDEN_EVENT_PAIRS:
            if illegal_pair[0] in event_types and illegal_pair[1] in event_types:
                violations.append(ContractViolation(
                    "events",
                    f"非法事件组合: {illegal_pair[0]} 与 {illegal_pair[1]} 不能共存"
                ))
        for evt_type in event_types:
            if evt_type not in allowed_events:
                violations.append(ContractViolation(
                    "events",
                    f"task_state={task_state!r} 下不允许事件 {evt_type!r}"
                ))

    # G. 事件 sequence 连续性
    for e in events:
        if "sequence" not in e:
            violations.append(ContractViolation(
                "events[*].sequence",
                "每个事件必须有 sequence 字段"
            ))
            break

    if events and all("sequence" in e for e in events):
        event_tuples = [(e["sequence"], e.get("event"), e.get("task_id")) for e in events]
        # 按 sequence 排序
        sorted_events = sorted(event_tuples, key=lambda x: x[0])

        # 检查 task_id 一致性
        task_ids = {e[2] for e in sorted_events if e[2]}
        if len(task_ids) > 1:
            violations.append(ContractViolation(
                "events[*].task_id",
                f"同一事件流出现多个 task_id: {task_ids}"
            ))

        # 检查 sequence 从 1 开始，连续递增
        sequences = [e[0] for e in sorted_events]
        expected = list(range(1, len(sequences) + 1))
        if sequences != expected:
            violations.append(ContractViolation(
                "events[*].sequence",
                f"sequence 不连续，实际: {sequences}，预期: {expected}"
            ))

    return violations


def assert_no_violations(result: Dict[str, Any], test_name: str = ""):
    violations = validate_result_contract(result)
    if violations:
        msg = f"[{test_name}] 契约违规 ({len(violations)} 项):\n"
        for v in violations:
            msg += f"  - {v.field}: {v.message}\n"
        raise AssertionError(msg)


# ================================================================
# 7. EvidenceGate — 证据准入契约
# ================================================================
# 语义定义（五层分离）：
#   workspace_dependency   → 任务对工作区的依赖要求（ExecutionProfile）
#   requires_workspace_scan → LLM 提出的扫描需求（辅助信号）
#   workspace_available     → 系统是否具备读取工作区的能力
#   EvidenceGate.required   → Worker 综合判定：任务是否依赖工作区证据
#   EvidenceGate.acquired   → 实际文件读取是否成功且结果有效
#
# 关键约束：
#   - acquired=True 必须对应真实文件读取操作，不能由路由声明或非空对象推导
#   - required=True 但 acquired=False 时，禁止生成依赖源码证据的步骤输出

EVIDENCE_STATUS_NOT_REQUIRED = "not_required"
EVIDENCE_STATUS_PENDING      = "pending"
EVIDENCE_STATUS_ACQUIRED     = "acquired"
EVIDENCE_STATUS_FAILED       = "failed"
EVIDENCE_STATUS_PARTIAL      = "partial"

EVIDENCE_STATUS_ALL: Set[str] = {
    EVIDENCE_STATUS_NOT_REQUIRED,
    EVIDENCE_STATUS_PENDING,
    EVIDENCE_STATUS_ACQUIRED,
    EVIDENCE_STATUS_FAILED,
    EVIDENCE_STATUS_PARTIAL,
}

EVIDENCE_STATUSES_TERMINAL: Dict[str, bool] = {
    EVIDENCE_STATUS_NOT_REQUIRED: False,
    EVIDENCE_STATUS_PENDING:      False,
    EVIDENCE_STATUS_ACQUIRED:     True,
    EVIDENCE_STATUS_FAILED:       True,
    EVIDENCE_STATUS_PARTIAL:      True,
}


class EvidenceGate:
    """
    Worker 执行期的证据准入判定。

    生命周期由 Worker 管理，不由路由器定义。
    写入规则：
      - required:   Worker 在 analyze 后综合判定（LLM profile + 用户 prompt 正则）
      - acquired:   仅由实际读取操作成功时设为 True
      - status:     由 required 和 acquired 计算
      - files_read: 由实际读取操作填充，不得由其它方写入
      - search_hits:  由搜索操作填充
      - search_errors: 由搜索/读取操作填充
    """
    __slots__ = (
        "required", "acquired", "status",
        "failure_reason", "files_read", "search_hits",
        "search_errors",
    )

    def __init__(
        self,
        required: bool = False,
        acquired: bool = False,
        failure_reason: str = "",
        files_read: Optional[List[str]] = None,
        search_hits: int = 0,
        search_errors: Optional[List[str]] = None,
    ):
        self.required = required
        self.acquired = acquired
        self.failure_reason = failure_reason
        self.files_read = files_read or []
        self.search_hits = search_hits
        self.search_errors = search_errors or []
        self.status = self._compute_status()

    def _compute_status(self) -> str:
        if not self.required:
            return EVIDENCE_STATUS_NOT_REQUIRED
        if self.acquired:
            return EVIDENCE_STATUS_ACQUIRED
        if self.files_read and not self.acquired:
            return EVIDENCE_STATUS_PARTIAL
        if self.failure_reason:
            return EVIDENCE_STATUS_FAILED
        return EVIDENCE_STATUS_PENDING

    def is_terminal(self) -> bool:
        return EVIDENCE_STATUSES_TERMINAL.get(self.status, False)

    def can_proceed(self) -> bool:
        """
        是否可以继续执行依赖工作区证据的步骤。
        仅当不需要证据、或证据已充分获取时返回 True。
        """
        return not self.required or self.acquired

    def mark_acquired(self, files: List[str], hits: int = 0):
        self.acquired = True
        self.files_read = list(files)
        self.search_hits = hits
        self.failure_reason = ""
        self.search_errors = []
        self.status = self._compute_status()

    def mark_failed(self, reason: str, errors: Optional[List[str]] = None):
        if self.acquired:
            return
        self.acquired = False
        self.failure_reason = reason
        if errors:
            self.search_errors = list(errors)
        self.status = self._compute_status()

    def mark_partial(self, files: List[str], hits: int, reason: str):
        if self.acquired:
            return
        self.acquired = False
        self.files_read = list(files)
        self.search_hits = hits
        self.failure_reason = reason
        self.status = self._compute_status()

    def as_dict(self) -> Dict:
        return {
            "required": self.required,
            "acquired": self.acquired,
            "status": self.status,
            "failure_reason": self.failure_reason,
            "files_read": list(self.files_read),
            "search_hits": self.search_hits,
            "search_errors": list(self.search_errors),
        }

    def to_dict(self) -> Dict:
        return self.as_dict()

    @classmethod
    def from_dict(cls, d: Dict) -> "EvidenceGate":
        return cls(
            required=d.get("required", False),
            acquired=d.get("acquired", False),
            failure_reason=d.get("failure_reason", ""),
            files_read=list(d.get("files_read") or []),
            search_hits=d.get("search_hits", 0),
            search_errors=list(d.get("search_errors") or []),
        )

    def __repr__(self):
        return (
            f"EvidenceGate(required={self.required}, acquired={self.acquired}, "
            f"status={self.status!r}, files={len(self.files_read)}, hits={self.search_hits})"
        )


def validate_architecture_evidence(meta: Dict[str, Any]) -> EvidenceGate:
    """G5.1: 架构意图专用证据验证。

    规则：
      - 仅对 architecture intent 强制要求；其他 intent 返回 not_required。
      - 证据来源于本次任务 Capability Engine 的 arch.analyze 输出。
      - 必须验证字段类型、结构完整性、是否包含可分析模块。
      - 空依赖和空风险是合法结果，不导致失败。
      - 失败原因可区分：未执行、执行失败、格式异常、无有效模块。

    校验层级：
      R0  intent != "architecture" → not_required
      R1  架构证据缺失 → failed（区分 ARCH_NOT_EXECUTED / ARCH_EXECUTION_FAILED）
      R2  字段类型/结构异常 → failed
      R3  module_count == 0 + file_count > 0 → partial（阻断）
          module_count == 0 + file_count == 0 → failed
      R4  module_count > 0 → acquired
    """
    intent = meta.get("intent", "")

    # R0
    if intent != "architecture":
        return EvidenceGate(required=False)

    gate = EvidenceGate(required=True)
    arch_evidence = meta.get("architecture_evidence")

    # R1: 存在性
    if not arch_evidence or not isinstance(arch_evidence, dict):
        cap_results = meta.get("_capability_results", {})
        if isinstance(cap_results, dict) and "workspace.scan" in cap_results:
            gate.mark_failed(
                "架构分析执行失败：arch.analyze 执行异常，未产出有效输出"
            )
        else:
            gate.mark_failed(
                "架构分析未执行：Capability Engine 未产出 arch.analyze 结果"
            )
        return gate

    # R2: 必要数值字段 — 存在性 + 非 bool 类型 + 非负校验
    for field in ("file_count", "module_count"):
        value = arch_evidence.get(field)
        if value is None:
            gate.mark_failed(f"架构分析结果字段缺失：{field}")
            return gate
        if isinstance(value, bool) or not isinstance(value, int):
            gate.mark_failed(
                f"架构分析结果字段类型异常：{field} 应为 int，实际 {type(value).__name__}"
            )
            return gate
        if value < 0:
            gate.mark_failed(
                f"架构分析结果字段值异常：{field}={value}，不允许负值"
            )
            return gate

    # R2: 必要列表字段 — 存在性 + 类型校验
    for field in ("dependencies", "risks"):
        value = arch_evidence.get(field)
        if value is None:
            gate.mark_failed(f"架构分析结果字段缺失：{field}")
            return gate
        if not isinstance(value, list):
            gate.mark_failed(
                f"架构分析结果字段类型异常：{field} 应为 list，实际 {type(value).__name__}"
            )
            return gate

    # R2.1: dependencies 每个元素必须是二元组 (str, str)
    for i, dep in enumerate(arch_evidence["dependencies"]):
        if not isinstance(dep, (tuple, list)) or len(dep) != 2:
            gate.mark_failed(
                f"架构分析结果字段异常：dependencies[{i}] 格式非法，"
                f"应为二元组(str, str)，实际 {type(dep).__name__}"
            )
            return gate
        if not isinstance(dep[0], str) or not isinstance(dep[1], str):
            gate.mark_failed(
                f"架构分析结果字段异常：dependencies[{i}] 元素类型错误，"
                f"应为 (str, str)，实际 ({type(dep[0]).__name__}, {type(dep[1]).__name__})"
            )
            return gate

    # R2: layers — 存在性 + 类型
    layers = arch_evidence.get("layers")
    if layers is None or not isinstance(layers, dict):
        gate.mark_failed(
            f"架构分析结果字段缺失或类型异常：layers 应为 dict，实际 {type(layers).__name__}"
        )
        return gate

    # R2: 图字段 — 类型
    for field in ("mermaid_diagram", "ascii_diagram"):
        value = arch_evidence.get(field)
        if not isinstance(value, str):
            gate.mark_failed(
                f"架构分析结果字段类型异常：{field} 应为 str，实际 {type(value).__name__}"
            )
            return gate

    # R3: module_count == 0
    if arch_evidence["module_count"] == 0:
        if arch_evidence["file_count"] > 0:
            gate.mark_partial(
                files=["__arch_partial__"],
                hits=0,
                reason=(
                    f"架构分析未发现可识别模块：扫描 {arch_evidence['file_count']} 个文件，"
                    f"所有文件被跳过或无法解析"
                ),
            )
        else:
            gate.mark_failed("架构分析无效：未找到可分析的 Python 源文件")
        return gate

    # R4: 通过
    gate.mark_acquired(files=[], hits=arch_evidence["module_count"])
    return gate


# ================================================================
# G5.2: 路径穿越防护
# ================================================================

def _is_safe_subpath(workspace_path: str, file_path: str) -> bool:
    if not workspace_path or not file_path:
        return False
    try:
        ws_real = os.path.realpath(workspace_path)
        joined = os.path.normpath(os.path.join(workspace_path, file_path))
        full_real = os.path.realpath(joined)
        common = os.path.commonpath([ws_real, full_real])
        return os.path.normcase(common) == os.path.normcase(ws_real)
    except (OSError, ValueError, RuntimeError):
        return False


def validate_workspace_evidence(meta: Dict[str, Any]) -> EvidenceGate:
    """统一证据验证——步骤级与任务级共用同一套判定规则。

    规则：
      - 仅当 workspace_evidence 中存在非空字符串内容时视为有效证据。
      - ⭐ G4.3: 验证证据文件归属当前工作区且真实存在，防止跨工作区或已删除文件伪造证据。
      - 空字典或全部空值 → failed。
      - 调用方通过 gate.can_proceed() 判断是否放行。
    """
    ws_evidence = meta.get("workspace_evidence", {})
    evidence_hits = meta.get("evidence_search_hits", [])
    ws_path = meta.get("workspace_path", "")
    gate = EvidenceGate(required=True)
    valid_entries = {}
    skipped_entries = []
    for k, v in ws_evidence.items():
        if not isinstance(v, str) or not v.strip():
            continue
        if ws_path:
            if not _is_safe_subpath(ws_path, k):
                skipped_entries.append(k)
                continue
            full_path = os.path.join(ws_path, k)
            if not os.path.isfile(full_path):
                skipped_entries.append(k)
                continue
        valid_entries[k] = v
    if valid_entries:
        gate.mark_acquired(files=list(valid_entries.keys()), hits=len(evidence_hits))
    elif skipped_entries:
        gate.mark_failed(
            f"工作区证据文件不存在或不属于当前工作区: {', '.join(skipped_entries[:5])}"
        )
    else:
        gate.mark_failed("工作区证据未获取或无有效内容")
    return gate