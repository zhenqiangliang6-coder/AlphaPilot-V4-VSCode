# -*- coding: utf-8 -*-
"""
G5.1 契约测试 — architecture_evidence 验证

测试 validate_architecture_evidence(meta) 全部 14 个用例 (T1-T14)。

契约冻结规则：
  - 仅 architecture intent 强制要求架构证据
  - 证据来源于本次任务 Capability Engine 的 arch.analyze 输出
  - 空依赖/空风险为合法结果，不导致失败
  - partial 状态必须阻断 (can_proceed() == False)
  - 其他 intent 返回 not_required，不改变现有行为
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from task_state_contract import (
    EvidenceGate,
    validate_architecture_evidence,
    EVIDENCE_STATUS_NOT_REQUIRED,
    EVIDENCE_STATUS_ACQUIRED,
    EVIDENCE_STATUS_FAILED,
    EVIDENCE_STATUS_PARTIAL,
)


# ── 辅助函数 ──────────────────────────────────────────────────

def _make_arch_evidence(
    file_count=200,
    module_count=200,
    dependencies=None,
    layers=None,
    risks=None,
    mermaid_diagram="graph TD\n  A-->B",
    ascii_diagram="A -> B",
):
    return {
        "file_count": file_count,
        "module_count": module_count,
        "dependencies": dependencies if dependencies is not None else [],
        "layers": layers if layers is not None else {"core": ["module_a"]},
        "risks": risks if risks is not None else [],
        "mermaid_diagram": mermaid_diagram,
        "ascii_diagram": ascii_diagram,
    }


def _make_meta(intent="architecture", arch_evidence=None, cap_results=None):
    meta = {
        "intent": intent,
        "architecture_evidence": arch_evidence,
        "_capability_results": cap_results if cap_results is not None else {},
    }
    return meta


# ── T1 ─────────────────────────────────────────────────────────
# architecture intent + 有效证据 → acquired, can_proceed=True

def test_t1_valid_evidence_passes():
    meta = _make_meta(
        intent="architecture",
        arch_evidence=_make_arch_evidence(module_count=200),
        cap_results={"workspace.scan": {"file_count": 500}},
    )
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_ACQUIRED, f"T1: expected acquired, got {gate.status}"
    assert gate.can_proceed() is True, "T1: expected can_proceed=True"
    assert gate.search_hits == 200, f"T1: expected hits=200, got {gate.search_hits}"


# ── T2 ─────────────────────────────────────────────────────────
# architecture intent + module_count=0, file_count>0 → partial, can_proceed=False

def test_t2_no_modules_with_files_partial():
    meta = _make_meta(
        intent="architecture",
        arch_evidence=_make_arch_evidence(module_count=0, file_count=5),
        cap_results={"workspace.scan": {"file_count": 5}},
    )
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_PARTIAL, f"T2: expected partial, got {gate.status}"
    assert gate.can_proceed() is False, "T2: expected can_proceed=False"
    assert gate.required is True, "T2: expected required=True"


# ── T3 ─────────────────────────────────────────────────────────
# architecture intent + 证据缺失 + workspace.scan 不存在 → ARCH_NOT_EXECUTED

def test_t3_no_evidence_no_workspace_scan():
    meta = _make_meta(
        intent="architecture",
        arch_evidence=None,
        cap_results={},
    )
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_FAILED, f"T3: expected failed, got {gate.status}"
    assert gate.can_proceed() is False, "T3: expected can_proceed=False"
    assert "未执行" in gate.failure_reason, f"T3: reason should mention '未执行', got {gate.failure_reason}"


# ── T4 ─────────────────────────────────────────────────────────
# architecture intent + 证据缺失 + workspace.scan 存在 → ARCH_EXECUTION_FAILED

def test_t4_no_evidence_with_workspace_scan():
    meta = _make_meta(
        intent="architecture",
        arch_evidence=None,
        cap_results={"workspace.scan": {"file_count": 500}},
    )
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_FAILED, f"T4: expected failed, got {gate.status}"
    assert gate.can_proceed() is False, "T4: expected can_proceed=False"
    assert "执行失败" in gate.failure_reason, f"T4: reason should mention '执行失败', got {gate.failure_reason}"


# ── T5 ─────────────────────────────────────────────────────────
# architecture intent + 字段类型错误 → failed

def test_t5_wrong_field_type():
    meta = _make_meta(
        intent="architecture",
        arch_evidence=_make_arch_evidence(module_count="not_int"),
        cap_results={"workspace.scan": {"file_count": 500}},
    )
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_FAILED, f"T5: expected failed, got {gate.status}"
    assert gate.can_proceed() is False, "T5: expected can_proceed=False"
    assert "module_count" in gate.failure_reason, f"T5: reason should mention module_count, got {gate.failure_reason}"


# ── T6 ─────────────────────────────────────────────────────────
# write_code intent → not_required, can_proceed=True

def test_t6_write_code_not_required():
    meta = _make_meta(
        intent="write_code",
        arch_evidence=_make_arch_evidence(module_count=200),
    )
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_NOT_REQUIRED, f"T6: expected not_required, got {gate.status}"
    assert gate.can_proceed() is True, "T6: expected can_proceed=True"
    assert gate.required is False, "T6: expected required=False"


# ── T7 ─────────────────────────────────────────────────────────
# workspace_maintenance intent → not_required, can_proceed=True

def test_t7_workspace_maintenance_not_required():
    meta = _make_meta(
        intent="workspace_maintenance",
        arch_evidence=_make_arch_evidence(module_count=200),
    )
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_NOT_REQUIRED, f"T7: expected not_required, got {gate.status}"
    assert gate.can_proceed() is True, "T7: expected can_proceed=True"


# ── T8 ─────────────────────────────────────────────────────────
# chat intent → not_required, can_proceed=True

def test_t8_chat_not_required():
    meta = _make_meta(
        intent="chat",
        arch_evidence=None,
    )
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_NOT_REQUIRED, f"T8: expected not_required, got {gate.status}"
    assert gate.can_proceed() is True, "T8: expected can_proceed=True"


# ── T9 ─────────────────────────────────────────────────────────
# module_count = -1 → failed

def test_t9_negative_module_count():
    meta = _make_meta(
        intent="architecture",
        arch_evidence=_make_arch_evidence(module_count=-1),
        cap_results={"workspace.scan": {"file_count": 500}},
    )
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_FAILED, f"T9: expected failed, got {gate.status}"
    assert gate.can_proceed() is False, "T9: expected can_proceed=False"
    assert "负值" in gate.failure_reason, f"T9: reason should mention 负值, got {gate.failure_reason}"


# ── T10 ────────────────────────────────────────────────────────
# module_count = True (bool 冒充 int) → failed

def test_t10_bool_module_count():
    meta = _make_meta(
        intent="architecture",
        arch_evidence=_make_arch_evidence(module_count=True),
        cap_results={"workspace.scan": {"file_count": 500}},
    )
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_FAILED, f"T10: expected failed, got {gate.status}"
    assert gate.can_proceed() is False, "T10: expected can_proceed=False"
    assert "bool" in gate.failure_reason.lower() or "类型异常" in gate.failure_reason, \
        f"T10: reason should mention bool/类型异常, got {gate.failure_reason}"


# ── T11 ────────────────────────────────────────────────────────
# dependencies 元素不是二元关系 → failed

def test_t11_invalid_dependency_structure():
    evidence = _make_arch_evidence(module_count=5, dependencies=[("a",)])
    meta = _make_meta(
        intent="architecture",
        arch_evidence=evidence,
        cap_results={"workspace.scan": {"file_count": 500}},
    )
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_FAILED, f"T11: expected failed, got {gate.status}"
    assert gate.can_proceed() is False, "T11: expected can_proceed=False"
    assert "dependencies" in gate.failure_reason.lower() or "dependencies" in gate.failure_reason, \
        f"T11: reason should mention dependencies, got {gate.failure_reason}"


# ── T12 ────────────────────────────────────────────────────────
# workspace.scan 存在 + arch.analyze 缺失 → ARCH_EXECUTION_FAILED

def test_t12_workspace_scan_exists_but_arch_missing():
    meta = _make_meta(
        intent="architecture",
        arch_evidence=None,
        cap_results={"workspace.scan": {"file_count": 500}},
    )
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_FAILED, f"T12: expected failed, got {gate.status}"
    assert gate.can_proceed() is False, "T12: expected can_proceed=False"
    assert "执行失败" in gate.failure_reason or "执行异常" in gate.failure_reason, \
        f"T12: reason should indicate execution failure, got {gate.failure_reason}"


# ── T13 ────────────────────────────────────────────────────────
# 有效证据 + 空依赖 + 空风险 → acquired（合法空结果）

def test_t13_valid_with_empty_deps_and_risks():
    meta = _make_meta(
        intent="architecture",
        arch_evidence=_make_arch_evidence(
            module_count=5,
            dependencies=[],
            risks=[],
        ),
    )
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_ACQUIRED, f"T13: expected acquired, got {gate.status}"
    assert gate.can_proceed() is True, "T13: expected can_proceed=True"
    assert gate.search_hits == 5, f"T13: expected hits=5, got {gate.search_hits}"


# ── T14 ────────────────────────────────────────────────────────
# 非 architecture intent + 携带架构证据 → not_required

def test_t14_non_arch_with_arch_evidence_not_required():
    meta = _make_meta(
        intent="write_code",
        arch_evidence=_make_arch_evidence(module_count=200),
    )
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_NOT_REQUIRED, f"T14: expected not_required, got {gate.status}"
    assert gate.can_proceed() is True, "T14: expected can_proceed=True"


# ── 补充边界测试 ──────────────────────────────────────────────

def test_negative_file_count():
    meta = _make_meta(
        intent="architecture",
        arch_evidence=_make_arch_evidence(file_count=-5, module_count=10),
        cap_results={"workspace.scan": {"file_count": 500}},
    )
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_FAILED
    assert "负值" in gate.failure_reason


def test_missing_layer_field():
    evidence = {
        "file_count": 10,
        "module_count": 3,
        "dependencies": [],
        "risks": [],
        "mermaid_diagram": "graph TD",
        "ascii_diagram": "",
    }
    meta = _make_meta(intent="architecture", arch_evidence=evidence)
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_FAILED
    assert "layers" in gate.failure_reason.lower()


def test_dependency_element_wrong_type():
    evidence = _make_arch_evidence(
        module_count=5,
        dependencies=[(1, "b")],  # 第一个元素是 int，不是 str
    )
    meta = _make_meta(intent="architecture", arch_evidence=evidence)
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_FAILED


def test_layers_not_dict():
    evidence = _make_arch_evidence(layers=["not_a_dict"])
    meta = _make_meta(intent="architecture", arch_evidence=evidence)
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_FAILED
    assert "layers" in gate.failure_reason


def test_risks_not_list():
    evidence = _make_arch_evidence(risks="not_a_list")
    meta = _make_meta(intent="architecture", arch_evidence=evidence)
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_FAILED
    assert "risks" in gate.failure_reason


def test_cap_results_none_still_distinguishes():
    meta = {
        "intent": "architecture",
        "architecture_evidence": None,
        "_capability_results": None,
    }
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_FAILED
    assert "未执行" in gate.failure_reason


def test_file_count_zero_module_count_zero():
    meta = _make_meta(
        intent="architecture",
        arch_evidence=_make_arch_evidence(file_count=0, module_count=0),
    )
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_FAILED
    assert "Python 源文件" in gate.failure_reason


def test_empty_intent_not_required():
    meta = _make_meta(intent="", arch_evidence=None)
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_NOT_REQUIRED
    assert gate.can_proceed() is True


def test_missing_intent_field_not_required():
    meta = {"architecture_evidence": _make_arch_evidence(module_count=200)}
    gate = validate_architecture_evidence(meta)
    assert gate.status == EVIDENCE_STATUS_NOT_REQUIRED
    assert gate.can_proceed() is True


# ── 回归测试：workspace_evidence gate 不受影响 ────────────────
# 验证新增的 meta 字段不会破坏现有 validate_workspace_evidence

def test_workspace_evidence_gate_ignores_new_meta_fields():
    from task_state_contract import validate_workspace_evidence
    meta = {
        "workspace_evidence": {},
        "workspace_path": "",
        "_capability_results": {"workspace.scan": {"file_count": 500}},
        "architecture_evidence": _make_arch_evidence(module_count=200),
        "intent": "architecture",
    }
    gate = validate_workspace_evidence(meta)
    # 没有真实文件 → failed，但不应因新增字段而崩溃
    assert gate.status == EVIDENCE_STATUS_FAILED
    assert gate.can_proceed() is False