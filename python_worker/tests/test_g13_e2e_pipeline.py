# -*- coding: utf-8 -*-
"""G1.3 端到端任务流测试：验证能力结果穿透完整管道。

覆盖：
  1. Skill 路由："读取项目结构" 命中 workspace.project-structure
  2. 能力管道：scan → tree → mermaid 全链路
  3. Prompt 注入：已验证结果出现在 LLM prompt 中
  4. 错误隔离：Mermaid 失败不抹掉 TreeResult
  5. 文件副作用：只读能力不产生文件
  6. 降级场景：能力不可用时 LLM 仍可工作
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skills import route_skill, reload_skills
from capabilities.scan_workspace import scan_workspace, TreeResult
from capabilities.render_structure import tree_to_text, tree_to_mermaid
from capability_registry import get_registry, reset_registry
from capability_executor import resolve_and_execute_capabilities


# ─── fixtures ─────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reload():
    reload_skills()


@pytest.fixture
def temp_project():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "src").mkdir()
        (root / "src" / "core").mkdir()
        (root / "src" / "core" / "main.py").write_text("print('hello')")
        (root / "src" / "utils.py").write_text("def helper(): pass")
        (root / "tests").mkdir()
        (root / "tests" / "test_main.py").write_text("def test_main(): pass")
        (root / "README.md").write_text("# My Project")
        (root / "requirements.txt").write_text("flask==2.0.0")
        (root / ".gitignore").write_text("*.pyc\n__pycache__")
        (root / ".venv").mkdir()
        (root / ".venv" / "pip.exe").write_text("")
        (root / "__pycache__").mkdir()
        (root / "__pycache__" / "main.cpython-311.pyc").write_text("")
        (root / "node_modules").mkdir()
        (root / "node_modules" / "package.json").write_text("{}")
        yield tmp


# ─── Skill routing tests ──────────────────────────────────

class TestSkillRoutingG13:
    def test_structure_request_matches_correct_skill(self):
        matched = route_skill("帮我读取项目并画出项目结构图")
        assert matched is not None
        assert matched.id == "workspace.project-structure"
        assert "structure.tree" in matched.capabilities
        assert "structure.mermaid" in matched.capabilities

    def test_structure_request_does_not_match_writer_skill(self):
        matched = route_skill("帮我写一个sorter函数")
        if matched:
            assert matched.id != "workspace.project-structure"

    def test_various_structure_triggers(self):
        triggers_tests = [
            ("展示目录结构", True),
            ("show me the project structure", True),
            ("画出项目架构图", True),
            ("visualize the codebase", True),
            ("生成项目文件树", True),
            ("帮我写代码", False),
        ]
        for query, should_match in triggers_tests:
            matched = route_skill(query)
            is_structure = bool(matched and matched.id == "workspace.project-structure")
            assert is_structure == should_match, (
                f"query='{query}': expected match={should_match}, got={is_structure}"
            )

    def test_skill_has_readonly_capabilities_only(self):
        matched = route_skill("展示项目结构")
        assert matched is not None
        capabilities = set(matched.capabilities)
        assert "workspace.scan" in capabilities
        assert "structure.tree" in capabilities
        assert "structure.mermaid" in capabilities
        assert all(c.startswith("workspace.") or c.startswith("structure.") for c in capabilities)


# ─── Full pipeline tests ──────────────────────────────────

class TestFullPipeline:
    def test_pipeline_scan_tree_mermaid(self, temp_project):
        reset_registry()
        skill = route_skill("读取项目并画出结构图")
        assert skill is not None

        context = {}
        payload = {"workspace_path": temp_project}

        resolve_and_execute_capabilities(skill, context, payload)

        assert "_tree_result" in context
        assert "_capability_results" in context
        caps = context["_capability_results"]
        assert "workspace.scan" in caps
        assert "structure.tree" in caps
        assert "structure.mermaid" in caps

        tree_text = caps["structure.tree"]
        mermaid_src = caps["structure.mermaid"]

        assert "README.md" in tree_text
        assert "src" in tree_text
        assert "utils.py" in tree_text or "main.py" in tree_text
        assert mermaid_src.startswith("flowchart TD")

    def test_skip_patterns_respected(self, temp_project):
        reset_registry()
        skill = route_skill("展示项目结构")
        context = {}
        payload = {"workspace_path": temp_project}

        resolve_and_execute_capabilities(skill, context, payload)

        tree_text = context["_capability_results"]["structure.tree"]
        assert ".venv" not in tree_text
        assert "__pycache__" not in tree_text
        assert "node_modules" not in tree_text


# ─── Prompt injection test ─────────────────────────────────

class TestPromptInjection:
    def test_prompt_contains_capability_results(self, temp_project):
        """模拟 Worker prompt 构建：能力结果出现在 prompt 中。"""
        reset_registry()
        skill = route_skill("读取项目并画出结构图")
        context = {}
        payload = {"workspace_path": temp_project}

        resolve_and_execute_capabilities(skill, context, payload)

        capability_results = context.get("_capability_results", {})
        assert capability_results, "capability_results should not be empty"

        prompt = "用户的原始需求：展示项目结构"
        if capability_results:
            parts = ["\n\n[系统能力扫描结果]\n"]
            if "structure.tree" in capability_results:
                parts.append(
                    f"## 项目目录树 (ASCII)\n```text\n{capability_results['structure.tree']}\n```\n"
                )
            if "structure.mermaid" in capability_results:
                parts.append(
                    f"## 项目结构图 (Mermaid)\n```mermaid\n{capability_results['structure.mermaid']}\n```\n"
                )
            prompt += "".join(parts)

        assert "[系统能力扫描结果]" in prompt
        assert "```text" in prompt
        assert "```mermaid" in prompt
        assert "README.md" in prompt
        assert "flowchart TD" in prompt


# ─── Error isolation tests ─────────────────────────────────

class TestErrorIsolation:
    def test_tree_result_preserved_when_mermaid_would_fail(self, temp_project):
        """Mermaid 渲染失败不应该抹掉已经获取的 TreeResult。"""
        reset_registry()

        tree_result = scan_workspace(root_path=temp_project)
        assert isinstance(tree_result, TreeResult)
        assert tree_result.file_count > 0

        tree_text = tree_to_text(tree_result)
        assert tree_text

        with patch("capabilities.render_structure.tree_to_mermaid", side_effect=Exception("Mermaid crash")):
            try:
                mermaid_src = tree_to_mermaid(tree_result)
            except Exception:
                mermaid_src = None

        assert tree_result.file_count > 0
        assert tree_text
        assert "README.md" in tree_text


# ─── File side-effect tests ────────────────────────────────

class TestNoSideEffects:
    def test_capability_execution_creates_no_files(self, temp_project):
        before_files = _list_all_files(temp_project)

        reset_registry()
        skill = route_skill("读取项目并画出结构图")
        context = {}
        payload = {"workspace_path": temp_project}
        resolve_and_execute_capabilities(skill, context, payload)

        after_files = _list_all_files(temp_project)
        assert before_files == after_files, (
            f"Unexpected file changes:\n"
            f"  added: {after_files - before_files}\n"
            f"  removed: {before_files - after_files}"
        )

    def test_tree_result_contains_expected_files(self, temp_project):
        tree_result = scan_workspace(root_path=temp_project)
        tree_text = tree_to_text(tree_result)
        assert "README.md" in tree_text
        assert "requirements.txt" in tree_text
        assert "src" in tree_text
        assert "tests" in tree_text


# ─── Degradation tests ────────────────────────────────────

class TestDegradation:
    def test_missing_capability_does_not_crash(self):
        skill = route_skill("读取项目并画出结构图")

        reg = reset_registry()
        reg.unregister("structure.mermaid")

        context = {}
        payload = {"workspace_path": os.getcwd()}

        resolve_and_execute_capabilities(skill, context, payload)

    def test_invalid_workspace_path_does_not_crash(self):
        reset_registry()
        skill = route_skill("读取项目并画出结构图")
        context = {}
        payload = {"workspace_path": "Z:/nonexistent/path/12345"}
        resolve_and_execute_capabilities(skill, context, payload)

        assert "_capability_results" in context
        assert "workspace.scan" not in context.get("_capability_results", {})


# ─── Skill declaration tests ──────────────────────────────

class TestSkillDeclaration:
    def test_guidance_forbids_file_creation(self):
        skill = route_skill("读取项目并画出结构图")
        assert skill is not None
        guidance_lower = skill.guidance.casefold()
        assert "不" in skill.guidance
        assert "不要创建" in skill.guidance or "不要执行" in skill.guidance
        assert "只读" in skill.guidance or "read" in guidance_lower

    def test_guidance_mentions_structure_mermaid(self):
        skill = route_skill("读取项目并画出结构图")
        assert skill is not None
        assert "mermaid" in skill.guidance.lower()
        assert "structure.tree" in skill.guidance.lower()


# ─── helpers ──────────────────────────────────────────────

def _list_all_files(root: str) -> set:
    result = set()
    for dirpath, dirnames, filenames in os.walk(root):
        for fname in filenames:
            rel = Path(dirpath, fname).relative_to(root)
            result.add(str(rel).replace("\\", "/"))
    return result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])