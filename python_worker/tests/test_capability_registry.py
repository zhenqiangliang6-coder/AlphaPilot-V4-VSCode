# -*- coding: utf-8 -*-
"""Unit tests for AlphaPilot OS Capability Layer (G1.1).

Coverage:
  - capability_registry: register / resolve_all / execute / validate_result
  - scan_workspace: basic scan, depth / node limits, truncation, error paths
  - render_structure: tree_to_text / tree_to_mermaid determinism
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capability_registry import (
    CapabilityExecutionError,
    CapabilityNotAvailable,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
    ResolvedCapabilities,
    get_registry,
    reset_registry,
)
from capabilities.scan_workspace import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_NODES,
    DEFAULT_SKIP_DIRS,
    TreeNode,
    TreeResult,
    WorkspaceScanError,
    scan_workspace,
)
from capabilities.render_structure import tree_to_mermaid, tree_to_text


# ─── Fixtures ───────────────────────────────────────────────

@pytest.fixture
def temp_project():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "src").mkdir()
        (root / "src" / "main.py").write_text("# main")
        (root / "src" / "utils.py").write_text("# utils")
        (root / "tests").mkdir()
        (root / "tests" / "test_main.py").write_text("# test")
        (root / "README.md").write_text("# README")
        (root / ".env").write_text("KEY=val")
        (root / ".git").mkdir()
        (root / "__pycache__").mkdir()
        yield str(root)


@pytest.fixture
def empty_temp():
    with tempfile.TemporaryDirectory() as tmp:
        yield str(tmp)


@pytest.fixture
def fresh_registry():
    registry = CapabilityRegistry()
    return registry


# ─── scan_workspace ─────────────────────────────────────────

class TestScanWorkspace:
    def test_basic_scan_returns_tree_result(self, temp_project):
        result = scan_workspace(temp_project, max_depth=3, max_nodes=100)
        assert isinstance(result, TreeResult)
        assert result.root_path == str(Path(temp_project).resolve())
        assert result.scan_timestamp
        assert result.file_count >= 4
        assert result.directory_count >= 3
        assert not result.truncated

    def test_root_node_is_directory(self, temp_project):
        result = scan_workspace(temp_project, max_depth=1, max_nodes=100)
        assert result.root.kind == "directory"
        assert result.root.name == Path(temp_project).name

    def test_skips_dot_dirs_except_env(self, temp_project):
        result = scan_workspace(temp_project, max_depth=2, max_nodes=100)

        def find_names(node):
            names = []
            for c in node.children:
                names.append(c.name)
                names.extend(find_names(c))
            return names

        all_names = find_names(result.root)
        assert ".git" not in all_names
        assert "__pycache__" not in all_names
        assert ".env" in all_names

    def test_max_depth_truncation(self, temp_project):
        result = scan_workspace(temp_project, max_depth=0, max_nodes=100)
        assert result.truncated

    def test_max_depth_1_lists_direct_files(self, temp_project):
        result = scan_workspace(temp_project, max_depth=1, max_nodes=100)
        assert result.truncated
        file_names = [c.name for c in result.root.children if c.kind == "file"]
        assert "README.md" in file_names

    def test_max_nodes_truncation(self, temp_project):
        result = scan_workspace(temp_project, max_depth=5, max_nodes=2)
        assert result.truncated
        assert result.total_nodes <= 2

    def test_empty_directory(self, empty_temp):
        result = scan_workspace(empty_temp, max_depth=3, max_nodes=100)
        assert result.file_count == 0
        assert result.directory_count == 1
        assert not result.truncated

    def test_nonexistent_path_raises(self):
        with pytest.raises(WorkspaceScanError, match="不存在"):
            scan_workspace("/nonexistent/path/xyz")

    def test_file_path_raises(self, temp_project):
        file_path = os.path.join(temp_project, "README.md")
        with pytest.raises(WorkspaceScanError, match="不是目录"):
            scan_workspace(file_path)

    def test_empty_root_raises(self):
        with pytest.raises(ValueError, match="不能为空"):
            scan_workspace("")

    def test_negative_max_depth_raises(self):
        with pytest.raises(ValueError, match="max_depth"):
            scan_workspace("/tmp", max_depth=-1)

    def test_zero_max_nodes_raises(self):
        with pytest.raises(ValueError, match="max_nodes"):
            scan_workspace("/tmp", max_nodes=0)

    def test_custom_skip_dirs(self, temp_project):
        result = scan_workspace(
            temp_project, max_depth=3, max_nodes=100, skip_dirs={"src"}
        )
        child_names = [c.name for c in result.root.children]
        assert "src" not in child_names

    def test_custom_skip_globs(self, temp_project):
        result = scan_workspace(
            temp_project, max_depth=3, max_nodes=100, skip_globs=["*.md"]
        )
        file_names = {c.name for c in result.root.children if c.kind == "file"}
        assert "README.md" not in file_names

    def test_tree_result_as_dict(self, temp_project):
        result = scan_workspace(temp_project, max_depth=2, max_nodes=100)
        d = result.as_dict()
        assert d["root_path"]
        assert d["scan_timestamp"]
        assert d["root"]["kind"] == "directory"
        assert isinstance(d["file_count"], int)

    def test_tree_node_properties(self, temp_project):
        result = scan_workspace(temp_project, max_depth=2, max_nodes=100)
        assert result.root.is_directory
        assert not result.root.is_file
        assert result.root.relative_path

    def test_default_constants(self):
        assert DEFAULT_MAX_DEPTH == 4
        assert DEFAULT_MAX_NODES == 500
        assert ".git" in DEFAULT_SKIP_DIRS


# ─── render_structure ───────────────────────────────────────

class TestRenderStructure:
    def test_tree_to_text_contains_root_name(self, temp_project):
        result = scan_workspace(temp_project, max_depth=2, max_nodes=100)
        text = tree_to_text(result)
        assert Path(temp_project).name in text

    def test_tree_to_text_contains_summary(self, temp_project):
        result = scan_workspace(temp_project, max_depth=2, max_nodes=100)
        text = tree_to_text(result)
        assert "files" in text
        assert "directories" in text

    def test_tree_to_text_truncated_marker(self, temp_project):
        result = scan_workspace(temp_project, max_depth=0, max_nodes=100)
        text = tree_to_text(result)
        assert "truncated" in text.lower()

    def test_tree_to_text_deterministic(self, temp_project):
        result1 = scan_workspace(temp_project, max_depth=2, max_nodes=100)
        result2 = scan_workspace(temp_project, max_depth=2, max_nodes=100)
        assert tree_to_text(result1) == tree_to_text(result2)

    def test_mermaid_contains_flowchart(self, temp_project):
        result = scan_workspace(temp_project, max_depth=2, max_nodes=100)
        mermaid = tree_to_mermaid(result)
        assert mermaid.startswith("flowchart TD")

    def test_mermaid_contains_edges(self, temp_project):
        result = scan_workspace(temp_project, max_depth=2, max_nodes=100)
        mermaid = tree_to_mermaid(result)
        assert " --> " in mermaid

    def test_mermaid_escapes_special_chars(self):
        class FakeNode:
            kind = "file"
            relative_path = "test"
            children = ()

        fake = TreeResult(
            root_path="/fake",
            scan_timestamp="2024-01-01T00:00:00+00:00",
            root=TreeNode(
                name="foo[bar]",
                relative_path="foo[bar]",
                kind="directory",
                children=(),
            ),
            file_count=0,
            directory_count=1,
            truncated=False,
            skipped_symlinks=0,
        )
        mermaid = tree_to_mermaid(fake)
        assert "foo#91;bar#93;/]" in mermaid or "foo#91;bar#93;" in mermaid

    def test_mermaid_deterministic(self, temp_project):
        result1 = scan_workspace(temp_project, max_depth=2, max_nodes=100)
        result2 = scan_workspace(temp_project, max_depth=2, max_nodes=100)
        assert tree_to_mermaid(result1) == tree_to_mermaid(result2)


# ─── CapabilityRegistry ─────────────────────────────────────

class TestCapabilityRegistry:
    def test_register_and_get(self, fresh_registry):
        fresh_registry.register("test.echo", lambda x: x, description="echo")
        spec = fresh_registry.get("test.echo")
        assert spec is not None
        assert spec.capability_id == "test.echo"
        assert spec.read_only is True

    def test_register_duplicate_raises(self, fresh_registry):
        fresh_registry.register("test.dup", lambda: None)
        with pytest.raises(ValueError, match="已注册"):
            fresh_registry.register("test.dup", lambda: None)

    def test_register_invalid_id_raises(self, fresh_registry):
        with pytest.raises(ValueError, match="格式无效"):
            fresh_registry.register("test echo", lambda: None)

    def test_register_empty_id_raises(self, fresh_registry):
        with pytest.raises(ValueError, match="不能为空"):
            fresh_registry.register("", lambda: None)

    def test_register_non_callable_raises(self, fresh_registry):
        with pytest.raises(ValueError, match="可调用"):
            fresh_registry.register("test.nope", "not_a_function")

    def test_unregister(self, fresh_registry):
        fresh_registry.register("test.remove", lambda: None)
        assert fresh_registry.unregister("test.remove") is True
        assert fresh_registry.get("test.remove") is None

    def test_unregister_missing(self, fresh_registry):
        assert fresh_registry.unregister("nonexistent") is False

    def test_list_ids(self, fresh_registry):
        fresh_registry.register("test.a", lambda: None)
        fresh_registry.register("test.b", lambda: None)
        ids = fresh_registry.list_ids()
        assert "test.a" in ids
        assert "test.b" in ids

    def test_resolve_all_success(self, fresh_registry):
        fresh_registry.register("cap.x", lambda: "x")
        fresh_registry.register("cap.y", lambda: "y")
        resolved = fresh_registry.resolve_all(("cap.x", "cap.y"))
        assert resolved.has("cap.x")
        assert resolved.has("cap.y")
        assert len(resolved.list_ids()) == 2

    def test_resolve_all_missing_raises(self, fresh_registry):
        fresh_registry.register("cap.a", lambda: None)
        with pytest.raises(CapabilityNotAvailable) as exc:
            fresh_registry.resolve_all(("cap.a", "cap.missing"))
        assert "cap.missing" in exc.value.missing

    def test_resolve_all_empty(self, fresh_registry):
        resolved = fresh_registry.resolve_all(())
        assert len(resolved.list_ids()) == 0

    def test_execute_success(self, fresh_registry):
        fresh_registry.register("test.echo", lambda **kw: kw.get("x"))
        resolved = fresh_registry.resolve_all(("test.echo",))
        result = fresh_registry.execute(resolved, "test.echo", x=42)
        assert result.success
        assert result.data == 42

    def test_execute_unresolved_raises(self, fresh_registry):
        fresh_registry.register("test.a", lambda: None)
        resolved = fresh_registry.resolve_all(("test.a",))
        with pytest.raises(CapabilityNotAvailable):
            fresh_registry.execute(resolved, "test.b")

    def test_execute_handler_error(self, fresh_registry):
        def failing():
            raise RuntimeError("boom")

        fresh_registry.register("test.fail", failing)
        resolved = fresh_registry.resolve_all(("test.fail",))
        result = fresh_registry.execute(resolved, "test.fail")
        assert not result.success
        assert "boom" in result.error

    def test_validate_result_success(self, fresh_registry):
        fresh_registry.register("test.int", lambda **kw: kw.get("n", 0),
                               output_schema="int")
        resolved = fresh_registry.resolve_all(("test.int",))
        raw = fresh_registry.execute(resolved, "test.int", n=7)
        validated = fresh_registry.validate_result(
            "test.int", raw, expected_output_type=int
        )
        assert validated.success
        assert validated.validated
        assert validated.data == 7

    def test_validate_result_type_mismatch(self, fresh_registry):
        fresh_registry.register("test.int", lambda **kw: "string")

        resolved = fresh_registry.resolve_all(("test.int",))
        raw = fresh_registry.execute(resolved, "test.int")
        validated = fresh_registry.validate_result(
            "test.int", raw, expected_output_type=int
        )
        assert not validated.success
        assert "类型不匹配" in validated.error

    def test_validate_result_failed_exec(self, fresh_registry):
        def failing():
            raise RuntimeError("fail")

        fresh_registry.register("test.fail", failing)
        resolved = fresh_registry.resolve_all(("test.fail",))
        raw = fresh_registry.execute(resolved, "test.fail")
        validated = fresh_registry.validate_result("test.fail", raw)
        assert not validated.success

    def test_validate_tree_result_root_path(self, fresh_registry, temp_project):
        fresh_registry.register(
            "workspace.scan",
            lambda **kw: scan_workspace(temp_project, max_depth=2, max_nodes=100),
            output_schema="TreeResult",
        )
        resolved = fresh_registry.resolve_all(("workspace.scan",))
        raw = fresh_registry.execute(resolved, "workspace.scan")
        validated = fresh_registry.validate_result(
            "workspace.scan", raw, expected_root_path=str(Path(temp_project).resolve())
        )
        assert validated.validated

    def test_validate_tree_result_wrong_root(self, fresh_registry, temp_project):
        fresh_registry.register(
            "workspace.scan",
            lambda **kw: scan_workspace(temp_project, max_depth=2, max_nodes=100),
            output_schema="TreeResult",
        )
        resolved = fresh_registry.resolve_all(("workspace.scan",))
        raw = fresh_registry.execute(resolved, "workspace.scan")
        validated = fresh_registry.validate_result(
            "workspace.scan", raw, expected_root_path="/wrong/path"
        )
        assert not validated.success


# ─── Global registry ────────────────────────────────────────

class TestGlobalRegistry:
    def setup_method(self):
        self.reg = reset_registry()

    def test_defaults_registered(self):
        self.reg = get_registry()
        ids = self.reg.list_ids()
        assert "workspace.scan" in ids
        assert "structure.tree" in ids
        assert "structure.mermaid" in ids

    def test_resolve_all_defaults(self):
        self.reg = get_registry()
        resolved = self.reg.resolve_all(
            ("workspace.scan", "structure.tree", "structure.mermaid")
        )
        assert len(resolved.list_ids()) == 3


# ─── Pipeline: scan → render (integration) ──────────────────

class TestPipeline:
    def test_scan_then_tree(self, temp_project):
        registry = get_registry()
        resolved = registry.resolve_all(
            ("workspace.scan", "structure.tree")
        )
        scan_result = registry.execute(
            resolved, "workspace.scan", root_path=temp_project, max_depth=2, max_nodes=100
        )
        validated = registry.validate_result(
            "workspace.scan", scan_result,
            expected_root_path=str(Path(temp_project).resolve()),
        )
        assert validated.validated
        tree_result = validated.data

        resolved2 = registry.resolve_all(("structure.tree",))
        tree_output = registry.execute(
            resolved2, "structure.tree", result=tree_result
        )
        assert tree_output.success
        assert Path(temp_project).name in tree_output.data
        assert "files" in tree_output.data

    def test_scan_then_mermaid(self, temp_project):
        registry = get_registry()
        resolved = registry.resolve_all(
            ("workspace.scan", "structure.mermaid")
        )
        scan_out = registry.execute(
            resolved, "workspace.scan", root_path=temp_project, max_depth=2, max_nodes=100
        )
        validated = registry.validate_result(
            "workspace.scan", scan_out,
            expected_root_path=str(Path(temp_project).resolve()),
        )
        assert validated.validated

        resolved2 = registry.resolve_all(("structure.mermaid",))
        mermaid_out = registry.execute(
            resolved2, "structure.mermaid", result=validated.data
        )
        assert mermaid_out.success
        assert mermaid_out.data.startswith("flowchart TD")
        assert " --> " in mermaid_out.data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])