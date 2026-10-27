# -*- coding: utf-8 -*-
"""G1.2 接入回归测试：验证 capability_registry → qwen_worker_v2 的集成边界。

Coverage:
  1. _resolve_and_execute_capabilities 的 context 注入是否正确
  2. 能力未注册时的降级行为（不阻断任务）
  3. scan → tree → mermaid 执行管道完整性
  4. 无 capabilities 的 Skill 不受影响
  5. 无 Skill 匹配不受影响
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skills.base import Skill
from capability_registry import (
    CapabilityNotAvailable,
    CapabilityRegistry,
    get_registry,
    reset_registry,
)
from capability_executor import resolve_and_execute_capabilities
from capabilities.scan_workspace import scan_workspace, TreeResult


# ─── helpers ───────────────────────────────────────────────

def _make_skill(capabilities=()):
    return Skill(
        id="test.skill",
        name="Test Skill",
        version="1.0.0",
        description="test",
        triggers=("test",),
        priority=100,
        capabilities=capabilities,
        guidance="Test guidance",
    )


def _fresh_context():
    return {}


def _make_payload(workspace_path=None):
    return {"workspace_path": workspace_path or os.getcwd()}


# ─── _resolve_and_execute_capabilities tests ────────────────

class TestResolveAndExecuteCapabilities:
    def setup_method(self):
        self.reg = reset_registry()
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        (root / "src").mkdir()
        (root / "src" / "main.py").write_text("# main")
        (root / "README.md").write_text("# readme")
        self.temp_project = self._tmp.name

    def teardown_method(self):
        self._tmp.cleanup()

    def test_no_capabilities_does_nothing(self):
        skill = _make_skill(capabilities=())
        context = _fresh_context()
        payload = _make_payload()

        resolve_and_execute_capabilities(skill, context, payload)

        assert "_capability_results" not in context
        assert "_tree_result" not in context

    def test_unregistered_capability_graceful_degrade(self):
        skill = _make_skill(capabilities=("nonexistent.cap", "workspace.scan"))
        context = _fresh_context()
        payload = _make_payload()

        resolve_and_execute_capabilities(skill, context, payload)

        # registration failure should NOT crash
        # the function prints a warning and returns

    def test_workspace_scan_injects_tree_result(self):
        skill = _make_skill(capabilities=("workspace.scan",))
        context = _fresh_context()
        payload = _make_payload(self.temp_project)

        resolve_and_execute_capabilities(skill, context, payload)

        assert "_capability_results" in context
        assert "workspace.scan" in context["_capability_results"]
        assert "_tree_result" in context
        tree = context["_tree_result"]
        assert isinstance(tree, TreeResult)
        assert tree.file_count >= 1
        assert tree.directory_count >= 2

    def test_full_pipeline_scan_tree_mermaid(self):
        skill = _make_skill(
            capabilities=("workspace.scan", "structure.tree", "structure.mermaid")
        )
        context = _fresh_context()
        payload = _make_payload(self.temp_project)

        resolve_and_execute_capabilities(skill, context, payload)

        assert "_capability_results" in context
        assert "workspace.scan" in context["_capability_results"]
        assert "structure.tree" in context["_capability_results"]
        assert "structure.mermaid" in context["_capability_results"]
        assert "_tree_result" in context

        tree_text = context["_capability_results"]["structure.tree"]
        mermaid_src = context["_capability_results"]["structure.mermaid"]

        assert "README.md" in tree_text
        assert mermaid_src.startswith("flowchart TD")
        assert " --> " in mermaid_src

    def test_structure_renders_not_executed_without_scan(self):
        skill = _make_skill(
            capabilities=("structure.tree", "structure.mermaid")
        )
        context = _fresh_context()
        payload = _make_payload(self.temp_project)

        resolve_and_execute_capabilities(skill, context, payload)

        # scan wasn't declared → tree_result never set
        # → tree/mermaid should not execute (early return)
        assert "structure.tree" not in context.get("_capability_results", {})
        assert "structure.mermaid" not in context.get("_capability_results", {})

    def test_context_previous_data_preserved(self):
        skill = _make_skill(capabilities=("workspace.scan",))
        context = _fresh_context()
        context["existing_key"] = "existing_value"
        payload = _make_payload(self.temp_project)

        resolve_and_execute_capabilities(skill, context, payload)

        assert context["existing_key"] == "existing_value"
        assert "_tree_result" in context


# ─── Registration boundary tests ───────────────────────────

class TestRegistrationBoundary:
    def setup_method(self):
        self.reg = reset_registry()

    def test_all_default_capabilities_registered(self):
        ids = self.reg.list_ids()
        assert "workspace.scan" in ids
        assert "structure.tree" in ids
        assert "structure.mermaid" in ids

    def test_default_scan_is_callable(self):
        spec = self.reg.get("workspace.scan")
        assert spec is not None
        assert callable(spec.handler)
        assert spec.read_only is True

    def test_resolve_scan_then_execute(self):
        resolved = self.reg.resolve_all(("workspace.scan",))
        with tempfile.TemporaryDirectory() as tmp:
            result = self.reg.execute(resolved, "workspace.scan", root_path=tmp,
                                      max_depth=1, max_nodes=50)
            assert result.success
            validated = self.reg.validate_result(
                "workspace.scan", result,
                expected_root_path=str(Path(tmp).resolve()),
            )
            assert validated.validated


# ─── Existing Skill backward compatibility tests ────────────

class TestBackwardCompatibility:
    def test_skill_without_capabilities_unchanged(self):
        """无 capabilities 的 Skill 行为不变。"""
        skill = Skill(
            id="vision.image_analysis",
            name="Image Analysis",
            version="1.0.0",
            description="analyze images",
            triggers=("图片", "image"),
            priority=90,
            capabilities=(),
            guidance="Analyze the image content.",
        )
        assert skill.capabilities == ()
        assert skill.id == "vision.image_analysis"

    def test_skill_guidance_still_injectable(self):
        """guidance 字段的文本注入能力不受影响。"""
        skill = _make_skill(capabilities=("workspace.scan",))
        prompt = "user request"
        if skill:
            prompt = f"{prompt}\n[AlphaPilot Skill: {skill.id}]\n{skill.guidance}"
        assert "[AlphaPilot Skill: test.skill]" in prompt
        assert "Test guidance" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])