# -*- coding: utf-8 -*-
# python_worker/contracts/skill_contract.py — 能力契约
# ---------------------------------------------------------
# 契约 1/3：Skill Contract
#
# 定义系统能做什么、如何证明它完成了任务。
#
# 核心语义：
#   - SkillContract 描述一个能力的完整约束（输入、输出、权限、时限、证据）
#   - SkillResult  是执行结果 + 证据包（不只有 exit_code）
#   - SkillStatus   区分 succeeded / failed / inconclusive
#   - EvidenceSet   结构化证据，不依赖单一点判定
#
# 第六条原则：Evidence = Proof（证据即证明）
#   命令退出码为 0 ≠ 任务成功。
#   测试进程返回 0 ≠ 实际执行了预期测试。
#   文件写入成功 ≠ 修改符合需求。
#
#   每个 Skill 返回结构化证据；验证层根据 success_criteria 判定。
#   证据不足时 → inconclusive，不强行标记成功。
# ---------------------------------------------------------

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


# =========================================================
# 1. 枚举类型
# =========================================================

class SkillStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    TIMED_OUT = "timed_out"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"


class EvidenceRequirement(str, Enum):
    NONE = "none"
    OPTIONAL = "optional"
    REQUIRED = "required"


# =========================================================
# 2. 证据模型
# =========================================================

@dataclass
class EvidenceItem:
    key: str
    value: Any
    source: str = ""          # e.g. "stdout_parse", "file_stat", "llm_claim"
    confidence: float = 1.0   # 0.0–1.0
    note: str = ""


@dataclass
class EvidenceSet:
    items: List[EvidenceItem] = field(default_factory=list)
    summary: str = ""

    def add(self, key: str, value: Any, source: str = "", confidence: float = 1.0):
        self.items.append(EvidenceItem(key=key, value=value, source=source, confidence=confidence))

    def get(self, key: str) -> Optional[EvidenceItem]:
        for item in self.items:
            if item.key == key:
                return item
        return None

    def has_all(self, required_keys: Set[str]) -> bool:
        keys_present = {item.key for item in self.items}
        return required_keys.issubset(keys_present)

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "items": [
                {"key": i.key, "value": i.value, "source": i.source,
                 "confidence": i.confidence, "note": i.note}
                for i in self.items
            ],
        }


@dataclass
class EvidencePolicy:
    required_evidence: Set[str] = field(default_factory=set)
    optional_evidence: Set[str] = field(default_factory=set)
    min_confidence: float = 0.5
    auto_extract_from_stdout: bool = False

    def validate(self, evidence: EvidenceSet) -> tuple:
        """返回 (passed, missing, low_confidence)"""
        if not self.required_evidence:
            return (True, [], [])
        missing = [k for k in self.required_evidence
                   if evidence.get(k) is None]
        low_conf = [i for i in evidence.items
                    if i.confidence < self.min_confidence
                    and i.key in self.required_evidence]
        return (len(missing) == 0 and len(low_conf) == 0, missing, low_conf)


# =========================================================
# 3. 成功判定
# =========================================================

@dataclass
class SuccessCriteria:
    exit_code_zero: bool = True
    evidence_required: Set[str] = field(default_factory=set)
    ignore_stderr: bool = False
    custom_predicate: Optional[str] = None


# =========================================================
# 4. 能力契约
# =========================================================

@dataclass
class SkillContract:
    capability: str                           # e.g. "compile", "test", "lint"

    # 输入输出约束
    input_schema: Dict[str, str] = field(default_factory=dict)
    output_schema: Dict[str, str] = field(default_factory=dict)

    # 权限与时限
    permission_set: Set[str] = field(default_factory=set)
    timeout_seconds: int = 300
    cancel_policy: str = "kill"  # "kill" | "wait" | "graceful"

    # 证据与判定
    evidence_policy: EvidencePolicy = field(default_factory=EvidencePolicy)
    success_criteria: SuccessCriteria = field(default_factory=SuccessCriteria)

    # 元数据
    description: str = ""
    version: str = "1.0"


# =========================================================
# 5. 技能执行结果
# =========================================================

@dataclass
class SkillResult:
    capability: str
    status: SkillStatus = SkillStatus.INCONCLUSIVE

    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0

    evidence: EvidenceSet = field(default_factory=EvidenceSet)
    contract: Optional[SkillContract] = None
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "capability": self.capability,
            "status": self.status.value,
            "exit_code": self.exit_code,
            "stdout": self.stdout[:5000] if self.stdout else "",
            "stderr": self.stderr[:2000] if self.stderr else "",
            "duration_seconds": self.duration_seconds,
            "evidence": self.evidence.to_dict(),
            "error": self.error,
        }

    @staticmethod
    def _evaluate_success(
        exit_code: int,
        criteria: SuccessCriteria,
        evidence: EvidenceSet,
        stderr: str,
    ) -> SkillStatus:
        if criteria.exit_code_zero and exit_code != 0:
            return SkillStatus.FAILED

        if criteria.required_evidence:
            passed, _, _ = EvidencePolicy(
                required_evidence=criteria.required_evidence
            ).validate(evidence)
            if not passed:
                return SkillStatus.INCONCLUSIVE

        return SkillStatus.SUCCEEDED


# =========================================================
# 6. 预定义技能契约
# =========================================================

SKILL_COMPILE = SkillContract(
    capability="compile",
    description="编译项目源码，检测语法和类型错误",
    input_schema={"workspace": "str"},
    output_schema={"success": "bool", "errors": "str[]"},
    permission_set={"filesystem:write", "subprocess:compile"},
    timeout_seconds=300,
    evidence_policy=EvidencePolicy(
        required_evidence={"compile_stdout", "exit_code"},
        optional_evidence={"warning_count", "source_files_compiled"},
    ),
    success_criteria=SuccessCriteria(
        exit_code_zero=True,
        evidence_required={"exit_code"},
    ),
)

SKILL_TEST = SkillContract(
    capability="test",
    description="运行项目测试套件，返回通过/失败计数",
    input_schema={"workspace": "str"},
    output_schema={"passed": "int", "failed": "int", "total": "int"},
    permission_set={"filesystem:read", "subprocess:test"},
    timeout_seconds=600,
    evidence_policy=EvidencePolicy(
        required_evidence={"test_total", "test_passed", "test_failed"},
        optional_evidence={"test_output", "coverage"},
        min_confidence=0.8,
    ),
    success_criteria=SuccessCriteria(
        exit_code_zero=True,
        evidence_required={"test_total"},
    ),
)

SKILL_LINT = SkillContract(
    capability="lint",
    description="静态分析代码质量和风格",
    input_schema={"workspace": "str"},
    output_schema={"issues": "int", "severity": "str"},
    permission_set={"filesystem:read", "subprocess:lint"},
    timeout_seconds=120,
    evidence_policy=EvidencePolicy(
        required_evidence={"lint_exit_code"},
        optional_evidence={"lint_issue_count"},
    ),
    success_criteria=SuccessCriteria(
        exit_code_zero=True,
    ),
)

SKILL_DEPS = SkillContract(
    capability="deps",
    description="安装项目依赖",
    input_schema={"workspace": "str"},
    output_schema={"installed": "bool", "package_count": "int"},
    permission_set={"filesystem:write", "subprocess:install", "network:outbound"},
    timeout_seconds=300,
    success_criteria=SuccessCriteria(
        exit_code_zero=True,
    ),
)

_NAMED_CONTRACTS: Dict[str, SkillContract] = {
    "compile": SKILL_COMPILE,
    "test": SKILL_TEST,
    "lint": SKILL_LINT,
    "deps": SKILL_DEPS,
}


def get_skill_contract(capability: str) -> Optional[SkillContract]:
    return _NAMED_CONTRACTS.get(capability.lower())


def register_skill_contract(contract: SkillContract):
    _NAMED_CONTRACTS[contract.capability] = contract


def list_skill_contracts() -> List[SkillContract]:
    return list(_NAMED_CONTRACTS.values())