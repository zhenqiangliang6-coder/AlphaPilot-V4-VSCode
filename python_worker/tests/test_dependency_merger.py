# -*- coding: utf-8 -*-
"""
AlphaPilot 依赖合并器单元测试
------------------------------
验证 merge_dependencies 的去重、多信号合并、摘要生成。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dependency_merger import (
    merge_dependencies,
    dependency_summary,
    format_dependency_report,
    _normalize,
    _parse_version,
)


# ============================================================
# 基础工具
# ============================================================
class TestNormalize:
    def test_lowercase(self):
        assert _normalize("NumPy") == "numpy"

    def test_strip_version(self):
        assert _normalize("requests>=2.28") == "requests"
        assert _normalize("flask==3.0.0") == "flask"
        assert _normalize("pandas~=1.5") == "pandas"

    def test_strip_extra(self):
        assert _normalize("uvicorn[standard]") == "uvicorn"

    def test_strip_whitespace(self):
        assert _normalize("  numpy  ") == "numpy"


class TestParseVersion:
    def test_exact(self):
        name, ver = _parse_version("requests==2.28.1")
        assert name == "requests"
        assert ver == "==2.28.1"

    def test_ge(self):
        name, ver = _parse_version("flask>=3.0")
        assert name == "flask"
        assert ver == ">=3.0"

    def test_no_version(self):
        name, ver = _parse_version("pandas")
        assert name == "pandas"
        assert ver is None


# ============================================================
# 核心合并逻辑
# ============================================================
class TestMergeDependencies:
    def test_empty_all_returns_empty(self):
        assert merge_dependencies() == []
        assert merge_dependencies({}, [], []) == []

    def test_manifest_only(self):
        result = merge_dependencies(
            manifest_deps={"numpy": "==1.24.0", "pandas": ">=2.0"},
        )
        assert len(result) == 2
        assert result[0].name == "numpy"
        assert result[0].sources == ["manifest"]
        assert result[0].version == "==1.24.0"
        assert result[1].name == "pandas"
        assert result[1].version == ">=2.0"

    def test_ast_import_only(self):
        result = merge_dependencies(
            inferred_deps=["numpy", "requests", "matplotlib"],
        )
        assert len(result) == 3
        assert all(e.sources == ["ast_import"] for e in result)

    def test_depends_only(self):
        result = merge_dependencies(
            depends_deps=["openpyxl", "pandas"],
        )
        assert len(result) == 2
        assert all(e.sources == ["depends"] for e in result)

    def test_merge_two_sources(self):
        result = merge_dependencies(
            manifest_deps={"numpy": "==1.24"},
            inferred_deps=["numpy", "requests"],
        )
        assert len(result) == 2
        numpy_entry = [e for e in result if e.name == "numpy"][0]
        assert sorted(numpy_entry.sources) == ["ast_import", "manifest"]
        assert numpy_entry.signal_count == 2
        assert numpy_entry.version == "==1.24"

        requests_entry = [e for e in result if e.name == "requests"][0]
        assert requests_entry.sources == ["ast_import"]
        assert requests_entry.signal_count == 1

    def test_merge_all_three_sources(self):
        result = merge_dependencies(
            manifest_deps={"pandas": ">=2.0"},
            inferred_deps=["numpy", "pandas"],
            depends_deps=["openpyxl", "pandas"],
        )
        pandas_entry = [e for e in result if e.name == "pandas"][0]
        assert sorted(pandas_entry.sources) == ["ast_import", "depends", "manifest"]
        assert pandas_entry.signal_count == 3

        assert len(result) == 3

    def test_case_insensitive_dedup(self):
        result = merge_dependencies(
            manifest_deps={"NumPy": "==1.24"},
            inferred_deps=["numpy"],
        )
        assert len(result) == 1
        assert result[0].name == "numpy"
        assert result[0].signal_count == 2

    def test_manifest_version_not_lost_on_merge(self):
        result = merge_dependencies(
            manifest_deps={"flask": "==3.0.0"},
            depends_deps=["flask", "sqlalchemy"],
        )
        flask_entry = [e for e in result if e.name == "flask"][0]
        assert flask_entry.version == "==3.0.0"


class TestDependencySummary:
    def test_summary_counts(self):
        entries = merge_dependencies(
            manifest_deps={"numpy": None, "pandas": None},
            inferred_deps=["numpy", "requests"],
            depends_deps=["openpyxl", "pandas"],
        )
        summary = dependency_summary(entries)
        assert summary["total"] == 4
        assert summary["by_source"]["manifest"] == 2
        assert summary["by_source"]["ast_import"] == 2
        assert summary["by_source"]["depends"] == 2
        assert summary["multi_signal"] == 2
        assert summary["all_three"] == 0

    def test_all_three_detected(self):
        entries = merge_dependencies(
            manifest_deps={"numpy": None},
            inferred_deps=["numpy"],
            depends_deps=["numpy"],
        )
        summary = dependency_summary(entries)
        assert summary["total"] == 1
        assert summary["all_three"] == 1

    def test_single_signal_sets(self):
        entries = merge_dependencies(
            manifest_deps={"a": None},
            inferred_deps=["b"],
            depends_deps=["c"],
        )
        summary = dependency_summary(entries)
        assert summary["manifest_only"] == 1
        assert summary["import_only"] == 1
        assert summary["depends_only"] == 1


class TestFormatReport:
    def test_no_deps(self):
        report = format_dependency_report([])
        assert "No dependencies detected" in report

    def test_has_content(self):
        entries = merge_dependencies(
            manifest_deps={"numpy": "==1.24"},
        )
        report = format_dependency_report(entries)
        assert "numpy" in report
        assert "manifest" in report