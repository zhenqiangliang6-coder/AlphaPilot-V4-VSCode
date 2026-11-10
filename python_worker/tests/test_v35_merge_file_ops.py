# -*- coding: utf-8 -*-
"""v3.5 merge_file_ops 工业级 FileOp 合并 + 多语言支持的测试"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from file_ops import (
    merge_file_ops,
    get_code_files,
    _is_code_file,
    CODE_EXTENSIONS,
    filter_valid_file_ops,
    create_file_op,
)


# =========================================================
# _is_code_file
# =========================================================

class TestIsCodeFile:
    def test_python(self):
        assert _is_code_file("main.py") is True
        assert _is_code_file("types.pyi") is True

    def test_java(self):
        assert _is_code_file("Main.java") is True
        assert _is_code_file("Utils.kt") is True

    def test_javascript_typescript(self):
        assert _is_code_file("index.js") is True
        assert _is_code_file("app.ts") is True
        assert _is_code_file("Component.tsx") is True
        assert _is_code_file("helper.mjs") is True

    def test_go_rust(self):
        assert _is_code_file("main.go") is True
        assert _is_code_file("lib.rs") is True

    def test_non_code(self):
        assert _is_code_file("style.css") is False
        assert _is_code_file("readme.md") is False
        assert _is_code_file("data.json") is False
        assert _is_code_file("image.png") is False
        assert _is_code_file("") is False

    def test_config_languages(self):
        assert _is_code_file("config.yaml") is True
        assert _is_code_file("config.yml") is True

    def test_code_extensions_frozenset(self):
        assert isinstance(CODE_EXTENSIONS, frozenset)
        assert ".py" in CODE_EXTENSIONS
        assert ".tsx" in CODE_EXTENSIONS
        assert ".java" in CODE_EXTENSIONS


# =========================================================
# get_code_files
# =========================================================

class TestGetCodeFiles:
    def test_mixed_languages(self):
        ops = [
            {"path": "backend/main.py", "content": "print(1)"},
            {"path": "frontend/App.tsx", "content": "const x = 1"},
            {"path": "src/Service.java", "content": "class S{}"},
            {"path": "style.css", "content": "body{}"},
            {"path": "readme.md", "content": "# Hi"},
            {"path": None},  # invalid
        ]
        result = get_code_files(ops)
        paths = [op["path"] for op in result]
        assert "backend/main.py" in paths
        assert "frontend/App.tsx" in paths
        assert "src/Service.java" in paths
        assert "style.css" not in paths
        assert "readme.md" not in paths

    def test_empty(self):
        assert get_code_files([]) == []

    def test_only_non_code(self):
        ops = [{"path": "style.css", "content": "body{}"}]
        assert get_code_files(ops) == []


# =========================================================
# merge_file_ops
# =========================================================

class TestMergeFileOps:
    def test_preserves_unchanged_files(self):
        context = {
            "final_file_ops": [
                {"path": "a.py", "content": "old_a"},
                {"path": "b.tsx", "content": "old_b"},
                {"path": "c.java", "content": "old_c"},
            ]
        }
        new_ops = [{"path": "a.py", "content": "new_a"}]
        merged = merge_file_ops(context, new_ops, source_step="test")

        assert len(merged) == 3
        paths = [op["path"] for op in merged]
        assert "b.tsx" in paths  # 保留
        assert "c.java" in paths  # 保留

        a_content = next(op["content"] for op in merged if op["path"] == "a.py")
        assert a_content == "new_a"  # 更新

    def test_no_new_ops_returns_existing(self):
        context = {"final_file_ops": [{"path": "a.py", "content": "x"}]}
        merged = merge_file_ops(context, [], source_step="test")
        assert len(merged) == 1
        assert merged[0]["content"] == "x"

    def test_all_replaced(self):
        context = {
            "final_file_ops": [
                {"path": "a.py", "content": "old_a"},
                {"path": "b.py", "content": "old_b"},
            ]
        }
        new_ops = [
            {"path": "a.py", "content": "new_a"},
            {"path": "b.py", "content": "new_b"},
        ]
        merged = merge_file_ops(context, new_ops, source_step="test")
        assert len(merged) == 2
        assert all(op["content"].startswith("new_") for op in merged)

    def test_cross_language_preservation(self):
        """v3.5 核心场景：refine 只输出 .py，但前端 .tsx 不被丢弃"""
        context = {
            "final_file_ops": [
                {"path": "backend/main.py", "content": "py"},
                {"path": "backend/routers/tasks.py", "content": "py2"},
                {"path": "frontend/src/App.tsx", "content": "tsx"},
                {"path": "frontend/src/components/TaskList.tsx", "content": "tsx2"},
            ]
        }
        # 模拟 refine 只输出 Python 文件的优化结果
        new_ops = [
            {"path": "backend/main.py", "content": "py_refined"},
            {"path": "backend/routers/tasks.py", "content": "py2_refined"},
        ]
        merged = merge_file_ops(context, new_ops, source_step="refine")

        assert len(merged) == 4  # 2 refined + 2 preserved
        paths = [op["path"] for op in merged]
        assert "frontend/src/App.tsx" in paths
        assert "frontend/src/components/TaskList.tsx" in paths

        # 验证前端内容未被篡改
        tsx_op = next(op for op in merged if op["path"] == "frontend/src/App.tsx")
        assert tsx_op["content"] == "tsx"

    def test_writes_to_both_keys(self):
        context = {}
        new_ops = [{"path": "a.py", "content": "x"}]
        merge_file_ops(context, new_ops)
        assert context["final_file_ops"] == new_ops
        assert context["file_ops"] == new_ops

    def test_falls_back_to_file_ops(self):
        context = {"file_ops": [{"path": "old.py", "content": "old"}]}
        new_ops = [{"path": "new.py", "content": "new"}]
        merged = merge_file_ops(context, new_ops)
        assert len(merged) == 2

    def test_dedup_by_path(self):
        context = {
            "final_file_ops": [
                {"path": "a.py", "content": "v1"},
                {"path": "a.py", "content": "v2"},  # duplicate path
            ]
        }
        new_ops = [{"path": "a.py", "content": "v3"}]
        merged = merge_file_ops(context, new_ops)
        # 两个旧版 a.py 都被替换，只剩 1 个 a.py
        assert len(merged) == 1
        assert merged[0]["content"] == "v3"