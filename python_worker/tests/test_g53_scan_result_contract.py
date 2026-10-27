# -*- coding: utf-8 -*-
"""
G5.3-B 契约测试 — 扫描结果状态与生命周期

冻结规则：
  G5.3-P2: 路径与执行状态分离 — 路径存在 ≠ 扫描成功
  G5.3-P3: 失败必须可观测 — 六种状态互不混淆
  G5.3-P4: 能力依赖必须显式 — 无共享变量冒充状态

六种状态：
  NOT_REQUESTED       — 当前任务未请求扫描
  NOT_EXECUTED        — 已有扫描意图但尚未执行
  BLOCKED             — 因路径缺失/授权失败/前置条件不满足而阻断
  FAILED              — 扫描执行失败或发生异常
  VALIDATION_FAILED   — 扫描返回结果但未通过结果验证
  SUCCEEDED           — 扫描与结果验证均成功

核心约束：
  - 未成功时不得生成可供下游当作有效证据的扫描结果。
  - 状态与数据分离：_tree_result 只存成功且通过验证的数据。
  - 空项目（file_count=0）≠ FAILED。
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capability_executor import (
    resolve_and_execute_capabilities,
    _execute_workspace_scan,
    _extract_workspace_path,
)
from capability_registry import (
    CapabilityRegistry,
    CapabilityResult,
    CapabilityNotAvailable,
    ResolvedCapabilities,
    get_registry,
)

# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════


def _make_payload(workspace_path=None):
    p = {"prompt": "test"}
    if workspace_path is not None:
        p["workspace_path"] = workspace_path
    return p


def _make_skill(capabilities=None):
    skill = MagicMock()
    skill.id = "test_skill"
    skill.capabilities = capabilities or []
    return skill


def _make_tree_result_stub(root_path="/fake/path", file_count=3, directory_count=2):
    """构建可通过验证的 TreeResult 存根。"""
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


def _make_empty_tree_result_stub(root_path="/fake/path"):
    """构建 file_count=0 的 TreeResult 存根（空项目）。"""
    return _make_tree_result_stub(root_path=root_path, file_count=0, directory_count=1)


# ═══════════════════════════════════════════════════════════════
# B1: 正常扫描 → SUCCEEDED
# ═══════════════════════════════════════════════════════════════


class TestScanSucceeded:
    """验证扫描成功的完整路径"""

    def test_b1_successful_scan_writes_tree_result_and_capability_results(self, tmp_path):
        """B1: 正常扫描 → SUCCEEDED, _tree_result 和 capability_results 均写入"""
        from capability_registry import ResolvedCapabilities

        (tmp_path / "mod.py").write_text("# module")

        skill = _make_skill(capabilities=["workspace.scan"])
        context = {}
        payload = {"workspace_path": str(tmp_path)}
        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name == "workspace.scan"
            mock_resolve.return_value = mock_resolved

            tree = _make_tree_result_stub(root_path=str(tmp_path))

            with patch.object(registry, "execute") as mock_execute:
                mock_execute.return_value = CapabilityResult(
                    capability_id="workspace.scan",
                    success=True,
                    data=tree,
                )

                with patch.object(registry, "validate_result") as mock_validate:
                    mock_validate.return_value = CapabilityResult(
                        capability_id="workspace.scan",
                        success=True,
                        data=tree,
                        validated=True,
                    )

                    resolve_and_execute_capabilities(skill, context, payload)

        assert "_tree_result" in context, "SUCCEEDED 时应写入 _tree_result"
        assert "_capability_results" in context
        assert "workspace.scan" in context["_capability_results"]
        cr = context["_capability_results"]["workspace.scan"]
        assert cr.get("status") == "succeeded", f"期望 status='succeeded'，实际: {cr.get('status')}"
        assert cr["file_count"] == 3
        assert cr["directory_count"] == 2
        assert not cr["truncated"]


# ═══════════════════════════════════════════════════════════════
# B2: 扫描器返回失败 → FAILED
# ═══════════════════════════════════════════════════════════════


class TestScanFailed:
    """验证扫描执行失败的契约"""

    def test_b2_scan_failure_no_tree_result_no_evidence(self, tmp_path):
        """B2: 扫描器返回失败 → FAILED, 不写入 _tree_result, 不产生证据"""
        from capability_registry import ResolvedCapabilities

        skill = _make_skill(capabilities=["workspace.scan"])
        context = {}
        payload = {"workspace_path": str(tmp_path)}
        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name == "workspace.scan"
            mock_resolve.return_value = mock_resolved

            with patch.object(registry, "execute") as mock_execute:
                mock_execute.return_value = CapabilityResult(
                    capability_id="workspace.scan",
                    success=False,
                    error="工作区路径不存在",
                )

                resolve_and_execute_capabilities(skill, context, payload)

        assert "_tree_result" not in context, (
            "FAILED 时不得写入 _tree_result（数据不可消费）"
        )
        ws = context.get("_capability_results", {}).get("workspace.scan")
        assert ws is not None, (
            "FAILED 状态应记录在 _capability_results 中"
        )
        assert ws.get("status") == "failed", (
            f"期望 status='failed'，实际: {ws.get('status')}"
        )
        assert ws.get("error"), "失败原因应可追溯"

    def test_b2b_scan_failure_error_is_preserved(self, tmp_path):
        """B2 补充: 失败原因应可追溯"""
        from capability_registry import ResolvedCapabilities

        skill = _make_skill(capabilities=["workspace.scan"])
        context = {}
        payload = {"workspace_path": str(tmp_path)}
        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name == "workspace.scan"
            mock_resolve.return_value = mock_resolved

            error_msg = "工作区路径不可读: /nonexistent/path"

            with patch.object(registry, "execute") as mock_execute:
                mock_execute.return_value = CapabilityResult(
                    capability_id="workspace.scan",
                    success=False,
                    error=error_msg,
                )

                resolve_and_execute_capabilities(skill, context, payload)

        cr = context.get("_capability_results", {}).get("workspace.scan")
        assert cr is not None, "失败状态应记录"
        assert error_msg in cr.get("error", ""), (
            f"失败原因应保存: 期望包含 '{error_msg}'，实际: {cr.get('error')}"
        )


# ═══════════════════════════════════════════════════════════════
# B3: 扫描器抛出异常 → 转化为可观测失败
# ═══════════════════════════════════════════════════════════════


class TestScanException:
    """验证扫描器异常的处理边界"""

    def test_b3_handler_exception_converted_to_failure(self, tmp_path):
        """B3: 扫描器抛出异常 → 由 registry.execute() 转化为 CapabilityResult(success=False)"""
        from capability_registry import ResolvedCapabilities

        skill = _make_skill(capabilities=["workspace.scan"])
        context = {}
        payload = {"workspace_path": str(tmp_path)}
        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name == "workspace.scan"
            mock_resolve.return_value = mock_resolved

            with patch.object(registry, "execute") as mock_execute:
                mock_execute.return_value = CapabilityResult(
                    capability_id="workspace.scan",
                    success=False,
                    error="ValueError: root_path 不能为空",
                )

                resolve_and_execute_capabilities(skill, context, payload)

        assert "_tree_result" not in context, (
            "B3 违规: 异常被静默吞没，但 _tree_result 不应存在"
        )

    def test_b3b_exception_does_not_produce_valid_evidence(self, tmp_path):
        """B3 补充: 异常后不得伪装成功"""
        from capability_registry import ResolvedCapabilities

        skill = _make_skill(capabilities=["workspace.scan"])
        context = {}
        payload = {"workspace_path": str(tmp_path)}
        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name == "workspace.scan"
            mock_resolve.return_value = mock_resolved

            with patch.object(registry, "execute") as mock_execute:
                mock_execute.return_value = CapabilityResult(
                    capability_id="workspace.scan",
                    success=False,
                    error="模拟异常",
                )

                resolve_and_execute_capabilities(skill, context, payload)

        # 验证没有写入有效证据
        cr = context.get("_capability_results", {})
        ws = cr.get("workspace.scan", {})
        if isinstance(ws, dict):
            # 如果有 scan_timestamp，就是异常路径下依然写入了有效数据
            has_timestamp = "scan_timestamp" in ws or "as_dict" in ws
            assert not has_timestamp, (
                "B3 违规: 扫描异常后仍写入了含 scan_timestamp 的证据数据"
            )


# ═══════════════════════════════════════════════════════════════
# B4: 结果验证失败 → VALIDATION_FAILED
# ═══════════════════════════════════════════════════════════════


class TestValidationFailed:
    """验证结果验证失败的契约"""

    def test_b4_validation_failure_blocks_evidence_consumption(self, tmp_path):
        """B4: 验证失败 → VALIDATION_FAILED, 原始扫描数据不得作为有效证据"""
        from capability_registry import ResolvedCapabilities

        (tmp_path / "mod.py").write_text("# module")

        skill = _make_skill(capabilities=["workspace.scan"])
        context = {}
        payload = {"workspace_path": str(tmp_path)}
        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name == "workspace.scan"
            mock_resolve.return_value = mock_resolved

            tree = _make_tree_result_stub(root_path=str(tmp_path))

            with patch.object(registry, "execute") as mock_execute:
                mock_execute.return_value = CapabilityResult(
                    capability_id="workspace.scan",
                    success=True,
                    data=tree,
                )

                with patch.object(registry, "validate_result") as mock_validate:
                    mock_validate.return_value = CapabilityResult(
                        capability_id="workspace.scan",
                        success=False,
                        error="root_path 不匹配: 期望 /a, 实际 /b",
                        validated=False,
                    )

                    resolve_and_execute_capabilities(skill, context, payload)

        assert "_tree_result" not in context, (
            "B4 违规: 验证失败后 _tree_result 存在\n"
            "原始扫描结果被错误地当作有效证据"
        )

    def test_b4b_validation_failure_recorded_in_capability_results(self, tmp_path):
        """B4 补充: 验证失败的状态应写入 _capability_results"""
        from capability_registry import ResolvedCapabilities

        (tmp_path / "mod.py").write_text("# module")

        skill = _make_skill(capabilities=["workspace.scan"])
        context = {}
        payload = {"workspace_path": str(tmp_path)}
        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name == "workspace.scan"
            mock_resolve.return_value = mock_resolved

            tree = _make_tree_result_stub(root_path=str(tmp_path))

            with patch.object(registry, "execute") as mock_execute:
                mock_execute.return_value = CapabilityResult(
                    capability_id="workspace.scan",
                    success=True,
                    data=tree,
                )

                with patch.object(registry, "validate_result") as mock_validate:
                    mock_validate.return_value = CapabilityResult(
                        capability_id="workspace.scan",
                        success=False,
                        error="root_path 不匹配",
                        validated=False,
                    )

                    resolve_and_execute_capabilities(skill, context, payload)

        cr = context.get("_capability_results", {}).get("workspace.scan")
        assert cr is not None, "VALIDATION_FAILED 状态应记录"
        assert cr.get("status") == "validation_failed", (
            f"期望 status='validation_failed'，实际: {cr.get('status')}"
        )


# ═══════════════════════════════════════════════════════════════
# B5: 未声明扫描能力 → NOT_REQUESTED
# ═══════════════════════════════════════════════════════════════


class TestNotRequested:
    """验证 NOT_REQUESTED 状态与 FAILED 的区分"""

    def test_b5_no_scan_capability_is_not_failed(self):
        """B5: 未声明扫描能力 → NOT_REQUESTED, 不应被误判为 FAILED"""
        skill = _make_skill(capabilities=[])  # 无任何能力声明
        context = {}
        payload = {"workspace_path": "/some/path"}

        resolve_and_execute_capabilities(skill, context, payload)

        assert "_tree_result" not in context, (
            "NOT_REQUESTED 时不应有 _tree_result"
        )
        # 验证：_capability_results 中没有 workspace.scan 键
        # 这与 FAILED 的缺失在语义上不同——但当前代码不区分两者
        # 此测试记录当前行为
        cr = context.get("_capability_results", {})
        has_ws_scan = "workspace.scan" in cr
        assert not has_ws_scan, (
            "NOT_REQUESTED 时不应写入 workspace.scan\n"
            "如果此断言失败，说明当前代码在 NOT_REQUESTED 时写入了结果"
        )

    def test_b5b_no_capabilities_at_all_not_requested(self):
        """B5 补充: 无 capabilities 属性也是 NOT_REQUESTED"""
        skill = MagicMock()
        skill.id = "no_caps"
        skill.capabilities = None  # 无能力属性

        context = {}
        payload = {"workspace_path": "/some/path"}

        resolve_and_execute_capabilities(skill, context, payload)

        assert "_tree_result" not in context
        assert "_capability_results" not in context, (
            "NOT_REQUESTED 时机上不应产生 capability_results"
        )

    def test_b5c_other_capabilities_not_scan(self, tmp_path):
        """B5 补充: Skill 声明了其他能力但未声明 workspace.scan → NOT_REQUESTED

        G5.3-E3 修复后：arch.analyze 可独立执行，但 workspace.scan 仍为 NOT_REQUESTED。
        """
        from capability_registry import ResolvedCapabilities

        skill = _make_skill(capabilities=["arch.analyze"])
        context = {}
        payload = {"workspace_path": str(tmp_path)}
        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.specs = {"arch.analyze": MagicMock()}
            mock_resolved.has.side_effect = lambda name: name == "arch.analyze"
            mock_resolve.return_value = mock_resolved

            with patch.object(registry, "execute") as mock_execute:
                mock_execute.return_value = CapabilityResult(
                    "arch.analyze", success=True, data=MagicMock(
                        file_count=1, module_count=1,
                        dependencies=[], layers={}, risks=[],
                        mermaid_diagram="graph TD", ascii_diagram="",
                    )
                )

                resolve_and_execute_capabilities(skill, context, payload)

        # NOT_REQUESTED：未请求 workspace.scan
        assert "_tree_result" not in context
        assert context.get("_capability_results", {}).get("workspace.scan") is None


# ═══════════════════════════════════════════════════════════════
# B6: 路径缺失导致扫描未执行 → BLOCKED
# ═══════════════════════════════════════════════════════════════


class TestBlocked:
    """验证 BLOCKED 状态的契约"""

    def test_b6_path_missing_should_block_scan(self, tmp_path):
        """B6: 路径缺失/路径为 None → BLOCKED, 不调用扫描器

        此测试检测 _extract_workspace_path 返回 None 时，resolve_and_execute_capabilities
        是否仍会调用 workspace.scan 的执行函数。
        """
        from capability_registry import ResolvedCapabilities

        skill = _make_skill(capabilities=["workspace.scan"])
        context = {}
        payload = {}  # 无 workspace_path
        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name == "workspace.scan"
            mock_resolve.return_value = mock_resolved

            # 拦截 os.getcwd() 以模拟 G5.3-A 修复后的行为
            # 修复后 _extract_workspace_path 应返回 None，而非 os.getcwd()
            with patch(
                "capability_executor._extract_workspace_path",
                return_value=None,
            ):
                with patch.object(registry, "execute") as mock_execute:
                    resolve_and_execute_capabilities(skill, context, payload)

                    # G5.3-P5: BLOCKED 时不得调用扫描器
                    scan_called = any(
                        call_args[0][1] == "workspace.scan"
                        for call_args in mock_execute.call_args_list
                        if len(call_args[0]) >= 2
                    )
                    if scan_called:
                        pytest.fail(
                            "G5.3-P5 违规: 路径缺失时仍然调用了 workspace.scan\n"
                            "BLOCKED 状态未生效"
                        )

    def test_b6b_blocked_no_tree_result(self, tmp_path):
        """B6 补充: BLOCKED 时不产生 _tree_result"""
        from capability_registry import ResolvedCapabilities

        skill = _make_skill(capabilities=["workspace.scan"])
        context = {}
        payload = {}  # 无路径
        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name == "workspace.scan"
            mock_resolve.return_value = mock_resolved

            with patch(
                "capability_executor._extract_workspace_path",
                return_value=None,
            ):
                with patch.object(registry, "execute") as mock_execute:
                    resolve_and_execute_capabilities(skill, context, payload)

        assert "_tree_result" not in context

    def test_b6c_blocked_state_recorded(self, tmp_path):
        """B6 补充: BLOCKED 状态应在 _capability_results 中记录"""
        from capability_registry import ResolvedCapabilities

        skill = _make_skill(capabilities=["workspace.scan"])
        context = {}
        payload = {}
        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name == "workspace.scan"
            mock_resolve.return_value = mock_resolved

            with patch(
                "capability_executor._extract_workspace_path",
                return_value=None,
            ):
                with patch.object(registry, "execute") as mock_execute:
                    resolve_and_execute_capabilities(skill, context, payload)

        cr = context.get("_capability_results", {})
        ws = cr.get("workspace.scan")
        assert ws is not None, "BLOCKED 状态应记录"
        assert ws.get("status") == "blocked", (
            f"期望 status='blocked'，实际: {ws.get('status')}"
        )


# ═══════════════════════════════════════════════════════════════
# B7: 扫描成功但结果为空 → SUCCEEDED (≠ FAILED)
# ═══════════════════════════════════════════════════════════════


class TestSucceededEmpty:
    """验证空项目 ≠ 失败"""

    def test_b7_empty_project_is_succeeded_not_failed(self, tmp_path):
        """B7: 扫描成功但 file_count=0 → SUCCEEDED, 不是 FAILED

        空项目是合法的扫描结果：目录存在、可读、无 Python 文件。
        是否满足架构分析需求应由 G5.3-C 的能力依赖契约决定。
        """
        from capability_registry import ResolvedCapabilities

        skill = _make_skill(capabilities=["workspace.scan"])
        context = {}
        payload = {"workspace_path": str(tmp_path)}
        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name == "workspace.scan"
            mock_resolve.return_value = mock_resolved

            empty_tree = _make_empty_tree_result_stub(root_path=str(tmp_path))

            with patch.object(registry, "execute") as mock_execute:
                mock_execute.return_value = CapabilityResult(
                    capability_id="workspace.scan",
                    success=True,
                    data=empty_tree,
                )

                with patch.object(registry, "validate_result") as mock_validate:
                    mock_validate.return_value = CapabilityResult(
                        capability_id="workspace.scan",
                        success=True,
                        data=empty_tree,
                        validated=True,
                    )

                    resolve_and_execute_capabilities(skill, context, payload)

        assert "_tree_result" in context, (
            "B7 违规: 空项目扫描成功后 _tree_result 缺失\n"
            "file_count=0 不应被当作 FAILED"
        )
        assert context["_capability_results"]["workspace.scan"]["file_count"] == 0
        assert context["_capability_results"]["workspace.scan"]["directory_count"] == 1
        assert not context["_capability_results"]["workspace.scan"]["truncated"]


# ═══════════════════════════════════════════════════════════════
# B8: 失败后重试 — 状态归属清晰
# ═══════════════════════════════════════════════════════════════


class TestRetryIsolation:
    """验证重试前后状态独立"""

    def test_b8_retry_context_independent_from_previous_success(self, tmp_path):
        """B8: 第一任务成功 → 第二任务扫描失败 → 第二任务无 _tree_result"""
        from capability_registry import ResolvedCapabilities

        registry = get_registry()

        # ---- 第一任务：成功 ----
        (tmp_path / "mod.py").write_text("# module")
        ctx1 = {}
        payload1 = {"workspace_path": str(tmp_path)}

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name == "workspace.scan"
            mock_resolve.return_value = mock_resolved

            tree = _make_tree_result_stub(root_path=str(tmp_path))

            with patch.object(registry, "execute") as mock_execute:
                mock_execute.return_value = CapabilityResult(
                    "workspace.scan", success=True, data=tree
                )
                with patch.object(registry, "validate_result") as mock_validate:
                    mock_validate.return_value = CapabilityResult(
                        "workspace.scan", success=True, data=tree, validated=True
                    )
                    resolve_and_execute_capabilities(
                        _make_skill(["workspace.scan"]), ctx1, payload1
                    )

        assert "_tree_result" in ctx1, "任务 1 应成功"

        # ---- 第二任务：扫描失败 ----
        ctx2 = {}
        payload2 = {"workspace_path": str(tmp_path / "nonexistent")}

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name == "workspace.scan"
            mock_resolve.return_value = mock_resolved

            with patch.object(registry, "execute") as mock_execute:
                mock_execute.return_value = CapabilityResult(
                    "workspace.scan",
                    success=False,
                    error="工作区路径不存在",
                )

                resolve_and_execute_capabilities(
                    _make_skill(["workspace.scan"]), ctx2, payload2
                )

        assert "_tree_result" not in ctx2, (
            "B8 违规: 扫描失败的任务 2 中出现了 _tree_result\n"
            "可能是从任务 1 泄漏的（每个任务使用独立 context dict 时不应发生）"
        )
        # 确认任务 1 的 _tree_result 未受影响
        assert "_tree_result" in ctx1, "任务 1 的 _tree_result 不应被影响"

    def test_b8b_retry_after_failure_has_fresh_context(self):
        """B8 补充: 两次失败任务的 context 独立"""
        from capability_registry import ResolvedCapabilities

        registry = get_registry()

        ctx1 = {}
        ctx2 = {}

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name == "workspace.scan"
            mock_resolve.return_value = mock_resolved

            with patch.object(registry, "execute") as mock_execute:
                mock_execute.return_value = CapabilityResult(
                    "workspace.scan", success=False, error="失败 1"
                )
                resolve_and_execute_capabilities(
                    _make_skill(["workspace.scan"]), ctx1, {"workspace_path": "/a"}
                )

            with patch.object(registry, "execute") as mock_execute:
                mock_execute.return_value = CapabilityResult(
                    "workspace.scan", success=False, error="失败 2"
                )
                resolve_and_execute_capabilities(
                    _make_skill(["workspace.scan"]), ctx2, {"workspace_path": "/b"}
                )

        assert "_tree_result" not in ctx1
        assert "_tree_result" not in ctx2
        # 两个独立的 context dict 自然隔离——此测试确认这一点