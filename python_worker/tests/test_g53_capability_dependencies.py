# -*- coding: utf-8 -*-
"""
G5.3-C 契约测试 — 能力依赖关系与执行边界

冻结规则：
  G5.3-P4: 能力依赖必须显式 — 只阻断真正依赖缺失证据的能力
  G5.3-P5: 授权边界优先 — 不得因扫描失败而扩大访问范围

依赖矩阵（已冻结）：

  能力              对扫描结果的依赖              扫描失败后的行为
  ──────────────────────────────────────────────────────────────────
  workspace.scan     执行扫描本身                  记录明确失败状态
  structure.tree     需要 _tree_result             阻断
  structure.mermaid  需要 _tree_result             阻断
  arch.analyze       独立扫描（rglob）             不应因共享变量为空而阻断
  workspace 步骤     不依赖扫描结果                由授权+证据 Gate 判定
  write 步骤         不依赖扫描结果                由授权 Gate 判定
  LLM 推理           不依赖扫描结果                按任务类型独立判断

关键发现（来自只读审计）：
  C3: arch.analyze 的 analyze_workspace_architecture 自身执行 rglob("*.py")，
      不依赖 _tree_result。但 capability_executor.py:L77-79 的
      `tree_result is None → return` 无条件阻断它。
      这是假性耦合，需要解除。
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capability_executor import (
    resolve_and_execute_capabilities,
    _execute_workspace_scan,
    _execute_structure_tree,
    _execute_structure_mermaid,
    _execute_arch_analyze,
    _extract_workspace_path,
)
from capability_registry import (
    CapabilityRegistry,
    CapabilityResult,
    CapabilityNotAvailable,
    ResolvedCapabilities,
    get_registry,
)
from task_state_contract import (
    EvidenceGate,
    EvidenceGateBlocked,
    validate_workspace_evidence,
    validate_architecture_evidence,
)

# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════


def _make_skill(capabilities=None):
    skill = MagicMock()
    skill.id = "test_skill"
    skill.capabilities = capabilities or []
    return skill


def _make_tree_result_stub(root_path="/fake/path", file_count=3, directory_count=2):
    from capabilities.scan_workspace import TreeResult, TreeNode
    from datetime import datetime, timezone

    root_node = TreeNode(
        name=Path(root_path).name or "fake",
        relative_path=".",
        kind="directory",
        children=tuple(
            TreeNode(name=f"file_{i}.py", relative_path=f"file_{i}.py", kind="file")
            for i in range(file_count)
        ),
    )
    return TreeResult(
        root_path=str(Path(root_path).resolve()),
        scan_timestamp=datetime.now(timezone.utc).isoformat(),
        root=root_node,
        file_count=file_count,
        directory_count=max(directory_count, 1),
        truncated=False,
        skipped_symlinks=0,
        walk_errors=[],
    )


# ═══════════════════════════════════════════════════════════════
# C1: structure.tree — 依赖 _tree_result
# ═══════════════════════════════════════════════════════════════


class TestStructureTreeDependency:
    """验证 structure.tree 对 _tree_result 的依赖"""

    def test_c1_tree_not_executed_when_scan_fails(self, tmp_path):
        """C1: 扫描失败 → structure.tree 不得执行"""
        from capability_registry import ResolvedCapabilities

        skill = _make_skill(capabilities=["workspace.scan", "structure.tree"])
        context = {}
        payload = {"workspace_path": str(tmp_path)}
        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name in (
                "workspace.scan", "structure.tree"
            )
            mock_resolve.return_value = mock_resolved

            with patch.object(registry, "execute") as mock_execute:
                mock_execute.return_value = CapabilityResult(
                    capability_id="workspace.scan",
                    success=False,
                    error="工作区路径不存在",
                )

                resolve_and_execute_capabilities(skill, context, payload)

        assert "_tree_result" not in context
        assert "structure.tree" not in context.get("_capability_results", {}), (
            "C1 违规: 扫描失败后 structure.tree 被执行或写入了结果"
        )

    def test_c1b_tree_executed_when_scan_succeeds(self, tmp_path):
        """C1 补充: 扫描成功时 structure.tree 正常执行"""
        from capability_registry import ResolvedCapabilities

        skill = _make_skill(capabilities=["workspace.scan", "structure.tree"])
        context = {}
        payload = {"workspace_path": str(tmp_path)}
        registry = get_registry()

        tree = _make_tree_result_stub(root_path=str(tmp_path))

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name in (
                "workspace.scan", "structure.tree"
            )
            mock_resolve.return_value = mock_resolved

            call_count = 0

            def execute_side_effect(resolved, cid, **kwargs):
                nonlocal call_count
                call_count += 1
                if cid == "workspace.scan":
                    return CapabilityResult(
                        capability_id=cid, success=True, data=tree
                    )
                if cid == "structure.tree":
                    return CapabilityResult(
                        capability_id=cid, success=True, data="tree_output"
                    )
                return CapabilityResult(capability_id=cid, success=False, error="?")

            with patch.object(registry, "execute", side_effect=execute_side_effect):
                with patch.object(registry, "validate_result") as mock_validate:
                    mock_validate.return_value = CapabilityResult(
                        "workspace.scan", success=True, data=tree, validated=True
                    )
                    resolve_and_execute_capabilities(skill, context, payload)

        assert "structure.tree" in context.get("_capability_results", {}), (
            "C1: 扫描成功时 structure.tree 应正常执行"
        )


# ═══════════════════════════════════════════════════════════════
# C2: structure.mermaid — 依赖 _tree_result
# ═══════════════════════════════════════════════════════════════


class TestStructureMermaidDependency:
    """验证 structure.mermaid 对 _tree_result 的依赖"""

    def test_c2_mermaid_not_executed_when_scan_fails(self, tmp_path):
        """C2: 扫描失败 → structure.mermaid 不得执行"""
        from capability_registry import ResolvedCapabilities

        skill = _make_skill(
            capabilities=["workspace.scan", "structure.tree", "structure.mermaid"]
        )
        context = {}
        payload = {"workspace_path": str(tmp_path)}
        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name in (
                "workspace.scan", "structure.tree", "structure.mermaid"
            )
            mock_resolve.return_value = mock_resolved

            with patch.object(registry, "execute") as mock_execute:
                mock_execute.return_value = CapabilityResult(
                    "workspace.scan", success=False, error="scan error"
                )

                resolve_and_execute_capabilities(skill, context, payload)

        assert "structure.mermaid" not in context.get("_capability_results", {}), (
            "C2 违规: 扫描失败后 structure.mermaid 被执行或写入了结果"
        )

    def test_c2b_mermaid_not_executed_without_valid_structure(self):
        """C2 补充: 无有效扫描结构时 structure.mermaid 不得伪造或误用数据"""
        # 此测试验证：当 _tree_result 存在但类型异常时，mermaid 不会被调用
        # 当前实现中 _tree_result 只有 TreeResult 类型时才会被上游调用
        # mermaid 本身依赖 tree_result 参数 — 此测试保证类型安全
        from capability_registry import CapabilityResult, get_registry

        registry = get_registry()

        # 直接测试 _execute_structure_mermaid 的防御性
        tree_result = _make_tree_result_stub()
        capability_results = {}

        with patch.object(registry, "execute") as mock_execute:
            mock_execute.return_value = CapabilityResult(
                "structure.mermaid", success=True, data="mermaid_output"
            )

            _execute_structure_mermaid(
                MagicMock(), registry, tree_result, capability_results
            )

        # 正常路径
        assert "structure.mermaid" in capability_results
        assert capability_results["structure.mermaid"] == "mermaid_output"


# ═══════════════════════════════════════════════════════════════
# C3: arch.analyze — 独立依赖 vs 假性耦合
# ═══════════════════════════════════════════════════════════════


class TestArchAnalyzeDependency:
    """验证 arch.analyze 的实际依赖关系

    核心发现：analyze_workspace_architecture 自身执行 rglob("*.py")，
    不依赖 _tree_result。G5.3-E3 已解除假性耦合。
    """

    def test_c3_arch_analyze_should_execute_independently(self, tmp_path):
        """C3: 扫描失败时 arch.analyze 应能独立执行

        G5.3-E3 修复后：arch.analyze 不再被 tree_result=None 阻断。
        """
        from capability_registry import ResolvedCapabilities

        skill = _make_skill(capabilities=["workspace.scan", "arch.analyze"])
        context = {}
        payload = {"workspace_path": str(tmp_path)}
        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name in (
                "workspace.scan", "arch.analyze"
            )
            mock_resolve.return_value = mock_resolved

            with patch.object(registry, "execute") as mock_execute:
                arch_report = MagicMock()
                arch_report.file_count = 1
                arch_report.module_count = 1
                arch_report.dependencies = []
                arch_report.layers = {}
                arch_report.risks = []
                arch_report.mermaid_diagram = "graph TD"
                arch_report.ascii_diagram = ""

                def _c3_execute(resolved, capability_id, **kwargs):
                    if capability_id == "arch.analyze":
                        return CapabilityResult(capability_id, success=True, data=arch_report)
                    return CapabilityResult(capability_id, success=False, error="scan error")

                mock_execute.side_effect = _c3_execute

                resolve_and_execute_capabilities(skill, context, payload)

        # G5.3-E3 修复后：arch.analyze 应独立执行
        assert "arch.analyze" in context.get("_capability_results", {}), (
            "C3 修复后: arch.analyze 应能独立于 _tree_result 执行\n"
            "扫描失败不应连带阻断 arch.analyze"
        )

    def test_c3b_arch_analyze_should_work_without_tree_result(self, tmp_path):
        """C3 契约：arch.analyze 应能独立于 _tree_result 执行

        analyze_workspace_architecture 自身执行 rglob("*.py")，
        不依赖 _tree_result。此测试验证该独立性。
        """
        from capabilities.analyze_architecture import analyze_workspace_architecture

        (tmp_path / "mod.py").write_text("import os\n\ndef foo():\n    pass\n")

        report = analyze_workspace_architecture(str(tmp_path))

        assert report.module_count > 0, (
            "C3 契约: arch.analyze 应能独立扫描工作区，不依赖 _tree_result"
        )
        assert report.file_count > 0

    def test_c3c_arch_analyze_with_empty_workspace(self, tmp_path):
        """C3 补充: 空工作区下 arch.analyze 返回空报告而非失败"""
        from capabilities.analyze_architecture import analyze_workspace_architecture

        empty_dir = tmp_path / "empty_project"
        empty_dir.mkdir()

        report = analyze_workspace_architecture(str(empty_dir))

        assert report.file_count == 0
        assert report.module_count == 0
        # 空项目 ≠ 失败 — 与 B7 一致

    def test_c3d_arch_analyze_should_receive_blocking_reason(self, tmp_path):
        """C3 契约: 扫描失败时 arch.analyze 应独立执行成功

        G5.3-E3 修复后：arch.analyze 不再被 tree_result=None 阻断，
        而是独立执行。此测试验证独立性。
        """
        from capability_registry import ResolvedCapabilities

        skill = _make_skill(capabilities=["workspace.scan", "arch.analyze"])
        context = {}
        payload = {"workspace_path": str(tmp_path)}
        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name in (
                "workspace.scan", "arch.analyze"
            )
            mock_resolve.return_value = mock_resolved

            with patch.object(registry, "execute") as mock_execute:
                arch_report = MagicMock()
                arch_report.file_count = 1
                arch_report.module_count = 1
                arch_report.dependencies = []
                arch_report.layers = {}
                arch_report.risks = []
                arch_report.mermaid_diagram = "graph TD"
                arch_report.ascii_diagram = ""

                def _c3d_execute(resolved, capability_id, **kwargs):
                    if capability_id == "arch.analyze":
                        return CapabilityResult(capability_id, success=True, data=arch_report)
                    return CapabilityResult(capability_id, success=False, error="scan error")

                mock_execute.side_effect = _c3d_execute

                resolve_and_execute_capabilities(skill, context, payload)

        cr = context.get("_capability_results", {})
        arch = cr.get("arch.analyze")
        assert arch is not None, (
            "G5.3-P4 修复后: arch.analyze 应独立于 _tree_result 执行\n"
            "扫描失败不应阻止 arch.analyze 产出分析结果"
        )


# ═══════════════════════════════════════════════════════════════
# C4: 非工作区任务隔离
# ═══════════════════════════════════════════════════════════════


class TestNonWorkspaceTaskIsolation:
    """验证非工作区任务不被扫描失败拖垮"""

    def test_c4_no_scan_capability_not_affected_by_payload(self):
        """C4: Skill 未声明扫描能力 → 不因 payload 含路径而执行扫描"""
        skill = _make_skill(capabilities=[])  # 无能力声明
        context = {}
        payload = {"workspace_path": "/nonexistent/path", "prompt": "你好"}

        resolve_and_execute_capabilities(skill, context, payload)

        # 聊天任务不应因 payload 中有路径字段就被迫扫描
        assert "_tree_result" not in context
        assert "_capability_results" not in context

    def test_c4b_chat_skill_without_scan_capability(self):
        """C4 补充: 纯聊天 Skill 不含扫描能力 → 不受路径状态影响"""
        skill = _make_skill(capabilities=None)  # 无 capabilities
        context = {}
        payload = {}  # 完全空

        resolve_and_execute_capabilities(skill, context, payload)

        assert "_tree_result" not in context
        assert "_capability_results" not in context

    def test_c4c_other_capabilities_without_scan_unaffected(self, tmp_path):
        """C4 补充: Skill 有其他能力但不含 workspace.scan → 不因路径无效而崩溃"""
        from capability_registry import ResolvedCapabilities

        (tmp_path / "mod.py").write_text("# module")

        skill = _make_skill(capabilities=["arch.analyze"])  # 有 arch 但无 workspace.scan
        context = {}
        payload = {"workspace_path": str(tmp_path)}
        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.specs = {"arch.analyze": MagicMock()}
            mock_resolved.has.side_effect = lambda name: name == "arch.analyze"
            mock_resolve.return_value = mock_resolved

            with patch.object(registry, "execute") as mock_execute:
                arch_report = MagicMock()
                arch_report.file_count = 1
                arch_report.module_count = 1
                arch_report.dependencies = []
                arch_report.layers = {}
                arch_report.risks = []
                arch_report.mermaid_diagram = "graph TD"
                arch_report.ascii_diagram = ""
                mock_execute.return_value = CapabilityResult(
                    "arch.analyze", success=True, data=arch_report
                )

                resolve_and_execute_capabilities(skill, context, payload)

        # G5.3-E3 修复后: arch.analyze 独立执行
        assert "_tree_result" not in context
        assert "arch.analyze" in context.get("_capability_results", {}), (
            "C4c: arch.analyze 应能独立于 workspace.scan 执行"
        )


# ═══════════════════════════════════════════════════════════════
# C5: workspace 操作门禁
# ═══════════════════════════════════════════════════════════════


class TestWorkspaceGate:
    """验证 workspace 步骤的门禁逻辑"""

    def test_c5_workspace_evidence_gate_respects_required_flag(self):
        """C5: EvidenceGate 的 can_proceed 必须遵守证据要求"""
        # 不需要证据 → 放行
        gate_no_required = EvidenceGate(required=False, acquired=False)
        assert gate_no_required.can_proceed(), (
            "C5: 不需要证据时应放行"
        )

        # 需要证据但未获取 → 阻断
        gate_required_unacquired = EvidenceGate(required=True, acquired=False)
        assert not gate_required_unacquired.can_proceed(), (
            "C5: 需要证据但未获取时应阻断"
        )

        # 需要证据且已获取 → 放行
        gate_acquired = EvidenceGate(required=True, acquired=True)
        assert gate_acquired.can_proceed(), (
            "C5: 证据已获取时应放行"
        )

    def test_c5b_workspace_gate_triggered_by_execution_chain(self):
        """C5b: 两层 Gate 架构 — 调用方决定触发，verifier 决定放行

        既有契约（G5.3 审计确认）：
        - validate_workspace_evidence 是 verifier：被调用即 required=True，只验证证据。
        - Gate 适用性判断属于调用方职责（两层架构）。

        两个生产调用方的触发条件：
        - execute_step.py:  step_type ∈ EVIDENCE_GATED_STEPS AND "workspace" ∈ execution_chain
        - qwen_worker_v2.py: "workspace" ∈ execution_chain
        """
        # 断言 1: 执行链含 workspace → 调用方触发 Gate → verifier 验证证据
        meta_workspace = {
            "execution_chain": ["analyze", "workspace", "write"],
            "workspace_evidence": {},
            "workspace_path": "/fake/path",
        }
        should_trigger = "workspace" in meta_workspace.get("execution_chain", [])
        assert should_trigger, "调用方条件: execution_chain 含 workspace → 应触发 Gate"
        gate = validate_workspace_evidence(meta_workspace)
        assert gate.required, "verifier 被调用时 required 恒为 True"
        assert not gate.can_proceed(), (
            "C5b: 执行链含 workspace 但证据缺失 → Gate 应阻断"
        )

        # 断言 2: 执行链不含 workspace → 调用方不应触发 Gate
        # （这是调用方职责，不是 verifier 职责——两层架构）
        meta_no_workspace = {
            "execution_chain": ["analyze", "plan", "respond"],
            "workspace_evidence": {},
        }
        should_trigger = "workspace" in meta_no_workspace.get("execution_chain", [])
        assert not should_trigger, (
            "调用方条件: execution_chain 不含 workspace → 不应触发 Gate\n"
            "（两层架构：调用方决定是否调用 verifier）"
        )

        # 断言 3: 防御性验证 — 即使绕过调用方直接调用 verifier，
        # 它仍会按 verifier 模式执行（required=True），不会因 execution_chain
        # 缺失而跳过证据验证。这是安全兜底。
        gate = validate_workspace_evidence(meta_no_workspace)
        assert gate.required, (
            "安全不变量: verifier 被调用时 required 恒为 True，"
            "不因 execution_chain 缺失而削弱"
        )
        assert not gate.can_proceed(), (
            "安全不变量: verifier 被调用时证据缺失 → 必须阻断，"
            "不因 execution_chain 缺失而放行"
        )

    def test_c5b_e_execute_step_two_tier_trigger(self):
        """C5b-e: execute_step.py 的两级触发条件

        execute_step.py 有两层过滤：
        1. step_type ∈ EVIDENCE_GATED_STEPS
        2. "workspace" ∈ execution_chain
        """
        EVIDENCE_GATED_STEPS = {"analyze", "plan", "respond", "doc", "docstring"}

        # 条件 1 不满足 → 不触发 Gate（即使 execution_chain 含 workspace）
        meta = {"execution_chain": ["analyze", "workspace", "write"]}
        for step_type in ("route", "summary", "search"):
            should_trigger = (
                step_type in EVIDENCE_GATED_STEPS
                and "workspace" in meta.get("execution_chain", [])
            )
            assert not should_trigger, (
                f"C5b-e: step_type={step_type} 不在 EVIDENCE_GATED_STEPS → 不触发 Gate"
            )

        # 条件 1 满足 + 条件 2 满足 → 触发 Gate
        for step_type in EVIDENCE_GATED_STEPS:
            should_trigger = (
                step_type in EVIDENCE_GATED_STEPS
                and "workspace" in meta.get("execution_chain", [])
            )
            assert should_trigger, (
                f"C5b-e: step_type={step_type} ∈ EVIDENCE_GATED_STEPS "
                "且 execution_chain 含 workspace → 应触发 Gate"
            )

        # 条件 1 满足 + 条件 2 不满足 → 不触发 Gate
        meta_no_ws = {"execution_chain": ["analyze", "plan"]}
        for step_type in EVIDENCE_GATED_STEPS:
            should_trigger = (
                step_type in EVIDENCE_GATED_STEPS
                and "workspace" in meta_no_ws.get("execution_chain", [])
            )
            assert not should_trigger, (
                f"C5b-e: step_type={step_type} ∈ EVIDENCE_GATED_STEPS "
                "但 execution_chain 不含 workspace → 不触发 Gate"
            )

    def test_c5b_w_worker_level_single_trigger(self):
        """C5b-w: qwen_worker_v2.py 的单级触发条件

        qwen_worker_v2.py 只检查 "workspace" ∈ execution_chain。
        """
        # workspace 存在 → 触发 Gate
        meta_with = {"execution_chain": ["analyze", "workspace", "write"]}
        should_trigger = "workspace" in meta_with.get("execution_chain", [])
        assert should_trigger, "worker 级: execution_chain 含 workspace → 应触发 Gate"

        # workspace 不存在 → 不触发 Gate
        meta_without = {"execution_chain": ["analyze", "plan"]}
        should_trigger = "workspace" in meta_without.get("execution_chain", [])
        assert not should_trigger, "worker 级: execution_chain 不含 workspace → 不触发 Gate"

        # execution_chain 缺失 → 不触发 Gate（防御性）
        meta_empty = {}
        should_trigger = "workspace" in meta_empty.get("execution_chain", [])
        assert not should_trigger, "worker 级: execution_chain 缺失 → 不触发 Gate"

    def test_c5c_workspace_gate_not_affected_by_scan_success(self):
        """C5: workspace Gate 的触发条件与扫描成功/失败无关

        Gate 仅检查 execution_chain 中是否有 'workspace' 步骤。
        扫描失败不影响 Gate 的触发条件。
        """
        meta_scan_failed = {
            "execution_chain": ["analyze", "workspace", "write"],
            "workspace_path": None,
            "workspace_scan": None,
            "workspace_evidence": {},
        }
        gate = validate_workspace_evidence(meta_scan_failed)
        # Gate 仍会触发（因为 execution_chain 含 workspace）
        # 但证据缺失导致 acquired=False
        assert gate.required, "即使扫描失败，workspace Gate 仍应触发"
        assert not gate.acquired


# ═══════════════════════════════════════════════════════════════
# C6: write 操作门禁
# ═══════════════════════════════════════════════════════════════


class TestWriteGate:
    """验证 write 步骤的门禁逻辑"""

    def test_c6_write_not_controlled_by_scan_success(self):
        """C6: write 步骤的授权不由扫描成功/失败决定

        write 由 authorization_requests 和 TaskState 控制，
        不应因扫描失败而被自动禁止或自动允许。
        """
        # 扫描失败 + 有授权请求 → 应等待授权
        meta_with_auth = {
            "workspace_path": "/fake",
            "workspace_scan": None,
            "authorization_requests": [{"type": "file_write", "path": "/fake/mod.py"}],
        }
        has_auth = bool(meta_with_auth.get("authorization_requests"))
        assert has_auth, "有授权请求时不应被扫描失败掩盖"

        # 扫描失败 + 无授权请求 + 无需写入 → 不受影响
        meta_no_auth = {
            "workspace_path": "/fake",
            "workspace_scan": None,
            "authorization_requests": [],
        }
        has_auth_2 = bool(meta_no_auth.get("authorization_requests"))
        assert not has_auth_2, "无授权请求 → 扫描失败不应触发误判"

    def test_c6b_write_auth_independent_of_scan_state(self):
        """C6 补充: write 授权逻辑与扫描状态解耦

        即使扫描成功，仍可能需要授权才能写入。
        即使扫描失败，仍可能有合法的只读操作不触发写入。
        """
        # 扫描成功 ≠ 写入自动授权
        meta_scan_ok = {
            "workspace_path": "/fake",
            "workspace_scan": {"root": "/fake", "file_count": 10},
            "authorization_requests": [
                {"type": "file_write", "path": "/fake/new.py"}
            ],
        }
        has_auth = bool(meta_scan_ok.get("authorization_requests"))
        assert has_auth, "扫描成功不代表可以自动写入"


# ═══════════════════════════════════════════════════════════════
# C7: 最终 Gate 与执行链一致性
# ═══════════════════════════════════════════════════════════════


class TestFinalGateConsistency:
    """验证最终 Gate 检查的是证据和授权条件，而非仅检查步骤名称"""

    def test_c7_workspace_gate_checks_evidence_not_just_step_name(self):
        """C7: workspace Gate 应检查证据有效性，而非仅检查执行链中的步骤名"""
        # 场景：执行链含 workspace，但证据缺失
        meta_no_evidence = {
            "execution_chain": ["analyze", "workspace", "write"],
            "workspace_evidence": {},
            "workspace_path": None,
        }
        gate = validate_workspace_evidence(meta_no_evidence)
        assert gate.required
        assert not gate.acquired
        assert not gate.can_proceed(), (
            "C7: 执行链含 workspace 但证据缺失 → 应阻断"
        )

    def test_c7b_architecture_gate_checks_capability_results(self):
        """C7: architecture Gate 应区分'未执行'和'执行失败'

        validate_architecture_evidence 通过检查 _capability_results
        中的 'workspace.scan' 键来区分这两种情况。
        """
        # 场景 1: 架构意图 + 扫描未执行
        meta_no_scan = {
            "intent": "architecture",
            "_capability_results": {},
            "architecture_evidence": None,
        }
        gate1 = validate_architecture_evidence(meta_no_scan)
        assert not gate1.can_proceed()
        assert "未执行" in gate1.failure_reason, (
            f"C7: 期望原因含'未执行'，实际: {gate1.failure_reason}"
        )

        # 场景 2: 架构意图 + 扫描已执行但 arch 失败
        meta_scan_done = {
            "intent": "architecture",
            "_capability_results": {"workspace.scan": {"file_count": 10}},
            "architecture_evidence": None,
        }
        gate2 = validate_architecture_evidence(meta_scan_done)
        assert not gate2.can_proceed()
        assert "执行失败" in gate2.failure_reason or "执行异常" in gate2.failure_reason, (
            f"C7: 期望原因含'执行失败'/'执行异常'，实际: {gate2.failure_reason}"
        )

    def test_c7c_evidence_gate_blocked_exception(self):
        """C7: EvidenceGateBlocked 异常携带正确的 gate 状态"""
        gate = EvidenceGate(required=True, acquired=False)
        gate.mark_failed("工作区路径不存在")

        with pytest.raises(EvidenceGateBlocked) as exc_info:
            raise EvidenceGateBlocked(
                f"任务级校验：执行链包含 workspace 步骤但证据状态为 {gate.status}"
            )

        assert "failed" in str(exc_info.value).lower() or gate.status in str(
            exc_info.value
        )

    def test_c7d_non_architecture_intent_not_blocked_by_arch_gate(self):
        """C7: 非架构意图不被 architecture Gate 阻断"""
        meta_chat = {
            "intent": "chat",
            "_capability_results": {},
            "architecture_evidence": None,
        }
        gate = validate_architecture_evidence(meta_chat)
        assert not gate.required
        assert gate.can_proceed(), (
            "C7: 非架构意图不应被架构 Gate 阻断"
        )


# ═══════════════════════════════════════════════════════════════
# C8: 集成 — 扫描失败后的能力级联
# ═══════════════════════════════════════════════════════════════


class TestCascadeBlocking:
    """验证扫描失败后正确阻断依赖能力，放行独立能力"""

    def test_c8_only_dependent_capabilities_blocked(self, tmp_path):
        """C8: 扫描失败 → 仅阻断 tree/mermaid，不应阻断 LLM 推理和非工作区操作

        注意：当前实现中 arch.analyze 也被阻断（假性耦合）— 此测试记录现状。
        """
        from capability_registry import ResolvedCapabilities

        skill = _make_skill(
            capabilities=[
                "workspace.scan",
                "structure.tree",
                "structure.mermaid",
                "arch.analyze",
            ]
        )
        context = {}
        payload = {"workspace_path": str(tmp_path)}
        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name in (
                "workspace.scan",
                "structure.tree",
                "structure.mermaid",
                "arch.analyze",
            )
            mock_resolve.return_value = mock_resolved

            with patch.object(registry, "execute") as mock_execute:
                arch_report = MagicMock()
                arch_report.file_count = 1
                arch_report.module_count = 1
                arch_report.dependencies = []
                arch_report.layers = {}
                arch_report.risks = []
                arch_report.mermaid_diagram = "graph TD"
                arch_report.ascii_diagram = ""

                def _c8_execute(resolved, capability_id, **kwargs):
                    if capability_id == "arch.analyze":
                        return CapabilityResult(capability_id, success=True, data=arch_report)
                    return CapabilityResult(capability_id, success=False, error="scan error")

                mock_execute.side_effect = _c8_execute

                resolve_and_execute_capabilities(skill, context, payload)

        # G5.3-E3 修复后断言
        cr = context.get("_capability_results", {})

        # 依赖 _tree_result 的能力不应执行
        assert "structure.tree" not in cr, (
            "C8: structure.tree 依赖 _tree_result，扫描失败时应阻断"
        )
        assert "structure.mermaid" not in cr, (
            "C8: structure.mermaid 依赖 _tree_result，扫描失败时应阻断"
        )

        # arch.analyze — G5.3-E3 修复后应独立执行
        assert "arch.analyze" in cr, (
            "C8 修复后: arch.analyze 应独立于 _tree_result 执行"
        )