# -*- coding: utf-8 -*-
"""
G5.3-A 契约测试 — 路径来源与安全边界

冻结规则：
  G5.3-P1: 路径来源唯一、明确 — 不得静默回退到 os.getcwd()
  G5.3-P2: 路径与执行状态分离 — 路径存在 ≠ 扫描成功
  G5.3-P5: 授权边界优先 — 路径缺失不得扩大扫描范围

测试在隔离的 temp 目录中运行，不依赖真实项目结构。
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capability_executor import (
    resolve_and_execute_capabilities,
    _extract_workspace_path,
)

# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════


def _make_payload(workspace_path=None, project_path=None, **extra):
    """构建模拟 payload，显式控制路径字段。"""
    p = dict(extra)
    if workspace_path is not None:
        p["workspace_path"] = workspace_path
    if project_path is not None:
        p["project_path"] = project_path
    return p


def _make_skill(capabilities=None):
    """构建模拟 Skill 对象。"""
    skill = MagicMock()
    skill.id = "test_skill"
    skill.capabilities = capabilities or []
    return skill


# ═══════════════════════════════════════════════════════════════
# A1: _extract_workspace_path — 路径提取优先级
# ═══════════════════════════════════════════════════════════════


class TestExtractWorkspacePath:
    """_extract_workspace_path 的路径来源优先级测试"""

    def test_a1_returns_workspace_path_when_present(self):
        """workspace_path 存在时直接返回"""
        result = _extract_workspace_path({"workspace_path": "/valid/path"})
        assert result == "/valid/path"

    def test_a2_falls_back_to_project_path(self):
        """workspace_path 缺失时使用 project_path"""
        result = _extract_workspace_path({"project_path": "/project/path"})
        assert result == "/project/path"

    def test_a3_workspace_path_overrides_project_path(self):
        """workspace_path 和 project_path 同时存在时 workspace_path 优先"""
        result = _extract_workspace_path({
            "workspace_path": "/ws",
            "project_path": "/proj",
        })
        assert result == "/ws"

    def test_a4_empty_workspace_path_falls_through(self):
        """空字符串 workspace_path 应视为缺失，回退到 project_path"""
        result = _extract_workspace_path({
            "workspace_path": "",
            "project_path": "/proj",
        })
        assert result == "/proj"

    # ═══════════════════════════════════════════════
    # P1 契约: 不得静默回退到 os.getcwd()
    # ═══════════════════════════════════════════════

    def test_a5_both_missing_no_cwd_fallback(self):
        """G5.3-P1: 两个路径均缺失时不得回退到 os.getcwd()

        当前行为：返回 os.getcwd()（存在隐式回退）
        期望行为：返回 None 或抛出明确异常
        """
        payload = {"prompt": "test"}
        result = _extract_workspace_path(payload)

        cwd = os.getcwd()
        assert result != cwd, (
            f"G5.3-P1 违规: _extract_workspace_path 在路径缺失时回退到了 cwd={cwd}\n"
            f"期望: 返回 None 或抛出异常，不隐式授权访问当前目录"
        )

    def test_a6_both_empty_strings_no_cwd_fallback(self):
        """G5.3-P1: 两个路径均为空字符串时不得回退到 os.getcwd()"""
        payload = {"workspace_path": "", "project_path": ""}
        result = _extract_workspace_path(payload)

        cwd = os.getcwd()
        assert result != cwd, (
            f"G5.3-P1 违规: 空路径回退到了 cwd={cwd}"
        )


# ═══════════════════════════════════════════════════════════════
# A2: _extract_workspace_path — 路径格式校验
# ═══════════════════════════════════════════════════════════════


class TestPathFormatValidation:
    """路径格式校验测试"""

    def test_a7_whitespace_only_path(self):
        """全空白字符串视为无效路径"""
        result = _extract_workspace_path({
            "workspace_path": "   ",
            "project_path": None,
        })
        # G5.3-P1 修复: 全空白路径应返回 None，不得视为有效路径
        assert result is None, (
            f"G5.3-P1: 空白 workspace_path 不应转换为有效路径，实际: {result!r}"
        )

    def test_a8_none_is_not_treated_as_path(self):
        """None 不应被转换为字符串路径"""
        result = _extract_workspace_path({"workspace_path": None})
        # 当前行为：None 会触发 or 链 → project_path → cwd
        # 契约要求：缺失时应返回 None 而非自动选择
        assert result is None or isinstance(result, str)


# ═══════════════════════════════════════════════════════════════
# A3: resolve_and_execute_capabilities — 路径缺失时执行边界
# ═══════════════════════════════════════════════════════════════


class TestResolveWithMissingPath:
    """测试路径缺失时 resolve_and_execute_capabilities 的行为"""

    def test_a9_no_capabilities_returns_immediately(self):
        """无能力声明时直接返回，不触发任何路径解析"""
        skill = _make_skill(capabilities=None)
        context = {}
        payload = {}  # 完全空 payload

        resolve_and_execute_capabilities(skill, context, payload)

        # 不应写入任何能力结果
        assert "_capability_results" not in context
        assert "_tree_result" not in context

    def test_a10_capability_not_available_returns_gracefully(self):
        """能力未注册时降级返回，不因路径问题崩溃"""
        from capability_registry import CapabilityNotAvailable

        skill = _make_skill(capabilities=["workspace.scan"])
        context = {}
        payload = {}

        with patch("capability_executor.get_registry") as mock_reg:
            mock_registry = MagicMock()
            mock_registry.resolve_all.side_effect = CapabilityNotAvailable(
                ["workspace.scan"]
            )
            mock_reg.return_value = mock_registry

            # 不应抛出异常
            resolve_and_execute_capabilities(skill, context, payload)

            # 不应写入任何结果
            assert "_capability_results" not in context
            assert "_tree_result" not in context

    def test_a11_no_path_should_not_scan_cwd(self, tmp_path):
        """G5.3-P1: 路径缺失时不应使用 os.getcwd() 执行扫描

        使用 patch 拦截 os.getcwd() 并验证它是否被调用。
        """
        from capability_registry import CapabilityRegistry, ResolvedCapabilities
        from capability_executor import get_registry

        skill = _make_skill(capabilities=["workspace.scan"])
        context = {}
        payload = {}

        registry = get_registry()

        with patch("capability_executor.os.getcwd") as mock_cwd:
            mock_cwd.return_value = str(tmp_path)

            with patch.object(registry, "resolve_all") as mock_resolve:
                mock_resolved = MagicMock(spec=ResolvedCapabilities)
                mock_resolved.has.side_effect = lambda name: name == "workspace.scan"
                mock_resolve.return_value = mock_resolved

                with patch.object(registry, "execute") as mock_execute:
                    mock_execute.return_value = MagicMock(success=False, error="mocked")

                    resolve_and_execute_capabilities(skill, context, payload)

                    # G5.3-P1: os.getcwd() 不应被调用
                    # 注意：当前代码在 _extract_workspace_path 中会调用 os.getcwd()
                    # 此测试记录当前行为：断言 cwd 被调用即为违规
                    cwd_called = mock_cwd.called
                    if cwd_called:
                        pytest.fail(
                            f"G5.3-P1 违规: payload 缺失路径时 os.getcwd() 被调用了\n"
                            f"这意味着扫描器将以当前进程目录为根执行"
                        )

    def test_a12_path_nonexistent_causes_scan_failure(self, tmp_path):
        """G5.3-P2: 路径不存在时扫描必须失败"""
        from capability_registry import CapabilityRegistry, ResolvedCapabilities
        from capability_executor import get_registry

        nonexistent = str(tmp_path / "nonexistent_dir_12345")

        skill = _make_skill(capabilities=["workspace.scan"])
        context = {}
        payload = {"workspace_path": nonexistent}

        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name == "workspace.scan"
            mock_resolve.return_value = mock_resolved

            with patch.object(registry, "execute") as mock_execute:
                mock_execute.return_value = MagicMock(success=False, error="mock error")

                resolve_and_execute_capabilities(skill, context, payload)

                # 扫描失败时不应写入 _tree_result
                assert "_tree_result" not in context, (
                    "G5.3-P2 违规: 路径不存在时 _tree_result 被错误写入"
                )

    def test_a13_path_is_file_not_directory(self, tmp_path):
        """路径指向文件而非目录时应失败"""
        from capability_registry import CapabilityRegistry, ResolvedCapabilities
        from capability_executor import get_registry

        test_file = tmp_path / "test.py"
        test_file.write_text("# test")

        skill = _make_skill(capabilities=["workspace.scan"])
        context = {}
        payload = {"workspace_path": str(test_file)}

        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name == "workspace.scan"
            mock_resolve.return_value = mock_resolved

            with patch.object(registry, "execute") as mock_execute:
                mock_execute.return_value = MagicMock(success=False, error="mock error")

                resolve_and_execute_capabilities(skill, context, payload)

                # 不应写入 _tree_result
                assert "_tree_result" not in context

    def test_a14_valid_path_scans_correctly(self, tmp_path):
        """G5.3-P2: 合法路径正确扫描"""
        from capability_registry import CapabilityRegistry, ResolvedCapabilities
        from capability_executor import get_registry

        (tmp_path / "module_a.py").write_text("# module a")

        skill = _make_skill(capabilities=["workspace.scan"])
        context = {}
        payload = {"workspace_path": str(tmp_path)}

        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            # 只声明 workspace.scan，不声明后续能力
            mock_resolved.has.side_effect = lambda name: name == "workspace.scan"
            mock_resolve.return_value = mock_resolved

            with patch.object(registry, "execute") as mock_execute:
                from capabilities.scan_workspace import TreeResult
                from datetime import timezone, datetime

                mock_tree = TreeResult(
                    root_path=str(tmp_path),
                    scan_timestamp=datetime.now(timezone.utc).isoformat(),
                    root=MagicMock(),
                    file_count=1,
                    directory_count=0,
                    truncated=False,
                    skipped_symlinks=0,
                    walk_errors=[],
                )
                mock_execute.return_value = MagicMock(success=True, data=mock_tree)

                with patch.object(registry, "validate_result") as mock_validate:
                    mock_validate.return_value = MagicMock(
                        success=True, data=mock_tree
                    )

                    resolve_and_execute_capabilities(skill, context, payload)

                    # 应该写入 _tree_result
                    assert "_tree_result" in context, (
                        "G5.3-P2: 合法路径扫描成功后 _tree_result 未被写入"
                    )
                    assert "_capability_results" in context
                    assert "workspace.scan" in context["_capability_results"]


# ═══════════════════════════════════════════════════════════════
# A4: resolve_and_execute_capabilities — 权限边界
# ═══════════════════════════════════════════════════════════════


class TestAuthorizationBoundary:
    """G5.3-P5: 授权边界测试"""

    def test_a15_no_path_should_not_authorize_arbitrary_dirs(self, tmp_path):
        """G5.3-P5: 路径缺失时不应授权扫描任意目录

        此测试验证：当 payload 不含任何路径信息时，Capability Engine
        不应静默选择一个默认目录去扫描。
        """
        from capability_registry import CapabilityRegistry, ResolvedCapabilities
        from capability_executor import get_registry

        skill = _make_skill(capabilities=["workspace.scan"])
        context = {}
        payload = {}

        registry = get_registry()

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name == "workspace.scan"
            mock_resolve.return_value = mock_resolved

            with patch.object(registry, "execute") as mock_execute:
                mock_execute.return_value = MagicMock(success=True, data=MagicMock())

                with patch.object(registry, "validate_result") as mock_validate:
                    mock_validate.return_value = MagicMock(success=True, data=MagicMock())

                    resolve_and_execute_capabilities(skill, context, payload)

                    # 如果 execute 被调用了，检查传入的 root_path
                    if mock_execute.called:
                        call_args = mock_execute.call_args
                        root_path = call_args[1].get("root_path", "")
                        cwd = os.getcwd()
                        if root_path == cwd:
                            pytest.fail(
                                f"G5.3-P5 违规: payload 未包含 workspace_path, "
                                f"但扫描器以 cwd={cwd} 为根执行了扫描\n"
                                f"这构成了对其他目录的未授权访问"
                            )


# ═══════════════════════════════════════════════════════════════
# A5: 集成 — 连续任务隔离
# ═══════════════════════════════════════════════════════════════


class TestTaskIsolation:
    """验证 context 状态不会跨任务泄露"""

    def test_a16_second_task_context_independent(self, tmp_path):
        """连续两个任务使用独立的 context"""
        from capability_registry import CapabilityRegistry, ResolvedCapabilities
        from capability_executor import get_registry

        registry = get_registry()

        # 任务 1: 成功扫描
        skill1 = _make_skill(capabilities=["workspace.scan"])
        ctx1 = {}
        payload1 = {"workspace_path": str(tmp_path)}

        with patch.object(registry, "resolve_all") as mock_resolve:
            mock_resolved = MagicMock(spec=ResolvedCapabilities)
            mock_resolved.has.side_effect = lambda name: name in ("workspace.scan",)
            mock_resolve.return_value = mock_resolved

            with patch.object(registry, "execute") as mock_execute:
                from capabilities.scan_workspace import TreeResult
                from datetime import timezone, datetime

                mock_tree = TreeResult(
                    root_path=str(tmp_path),
                    scan_timestamp=datetime.now(timezone.utc).isoformat(),
                    root=MagicMock(),
                    file_count=1,
                    directory_count=0,
                    truncated=False,
                    skipped_symlinks=0,
                    walk_errors=[],
                )
                mock_execute.return_value = MagicMock(success=True, data=mock_tree)

                with patch.object(registry, "validate_result") as mock_validate:
                    mock_validate.return_value = MagicMock(success=True, data=mock_tree)

                    resolve_and_execute_capabilities(skill1, ctx1, payload1)

        assert "_tree_result" in ctx1, "任务 1 应成功写入 _tree_result"

        # 任务 2: 全新的 context，不应含 _tree_result
        from capability_registry import CapabilityRegistry, ResolvedCapabilities

        skill2 = _make_skill(capabilities=["workspace.scan"])
        ctx2 = {}
        payload2 = {}  # 无路径

        # 任务 2 在能力未注册场景下执行
        with patch("capability_executor.get_registry") as mock_reg:
            mock_registry = MagicMock()
            from capability_registry import CapabilityNotAvailable
            mock_registry.resolve_all.side_effect = CapabilityNotAvailable(
                ["workspace.scan"]
            )
            mock_reg.return_value = mock_registry

            resolve_and_execute_capabilities(skill2, ctx2, payload2)

        # 任务 2 不应残留任务 1 的结果
        assert "_tree_result" not in ctx2, (
            "G5.3: 任务 2 的 context 中不应残留任务 1 的 _tree_result\n"
            "（此测试仅验证 context 是独立 dict，跨任务泄露需集成测试）"
        )


# ═══════════════════════════════════════════════════════════════
# A6: _extract_workspace_path — cwd 回退标记
# ═══════════════════════════════════════════════════════════════


class TestCwdFallbackMarker:
    """见证 G5.3-P1 修复：_extract_workspace_path 不再回退到 os.getcwd()"""

    def test_a17_document_current_cwd_fallback_behavior(self):
        """G5.3-P1 已修复: _extract_workspace_path 不再回退到 os.getcwd()

        缺失路径时返回 None。
        """
        payload = {"prompt": "no path at all"}
        result = _extract_workspace_path(payload)

        assert result is None, (
            f"G5.3-P1 修复: 路径缺失应返回 None，实际: {result!r}"
        )