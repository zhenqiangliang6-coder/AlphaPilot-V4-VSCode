import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from context_builder import inspect_python_project, read_project_context, read_requested_python_files


def test_reads_only_allowlisted_project_context(tmp_path):
    (tmp_path / "README.md").write_text("Run with python app.py", encoding="utf-8")
    (tmp_path / "start.ps1").write_text("python app.py", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_home(): pass", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=value", encoding="utf-8")

    context, sources = read_project_context(str(tmp_path))

    assert set(sources) == {"README.md", "start.ps1", "tests/test_app.py"}
    assert "Run with python app.py" in context
    assert "def test_home" in context
    assert "SECRET=value" not in context


def test_missing_workspace_returns_no_context():
    context, sources = read_project_context("")

    assert context == ""
    assert sources == []


def test_reads_only_python_files_named_in_the_request(tmp_path):
    source = tmp_path / "src" / "cli.py"
    source.parent.mkdir()
    source.write_text("print('broken')", encoding="utf-8")

    files = read_requested_python_files(str(tmp_path), "修复 src/cli.py 的语法错误")

    assert files == {"src/cli.py": "print('broken')"}


def test_rejects_paths_outside_the_workspace(tmp_path):
    files = read_requested_python_files(str(tmp_path), "修复 ../outside.py")

    assert files == {}


def test_reads_absolute_python_path_with_spaces_and_chinese_trailing_text(tmp_path):
    source = tmp_path / "src" / "cli.py"
    source.parent.mkdir()
    source.write_text("print('broken')", encoding="utf-8")
    prompt = f"帮我检查修复路径是{source}的文件代码错误？"

    files = read_requested_python_files(str(tmp_path), prompt)

    assert files == {"src/cli.py": "print('broken')"}


def test_inspects_project_python_and_returns_only_problem_sources(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    (tmp_path / "src" / "valid.py").write_text("def valid():\n    return True\n", encoding="utf-8")
    (tmp_path / "src" / "indentation.py").write_text(
        "if True:\n\tpass\n        pass\n",
        encoding="utf-8",
    )
    venv = tmp_path / ".venv" / "Lib" / "site-packages"
    venv.mkdir(parents=True)
    (venv / "ignored.py").write_text("def ignored(:\n", encoding="utf-8")

    result = inspect_python_project(str(tmp_path))

    assert result["python_file_count"] == 3
    assert {issue["path"] for issue in result["issues"]} == {
        "src/broken.py",
        "src/indentation.py",
    }
    assert result["fixable_issue_count"] == 2
    assert set(result["source_files"]) == {"src/broken.py", "src/indentation.py"}
    assert result["unavailable_fix_files"] == 0


def test_infers_third_party_dependencies_from_imports_without_install_manifest(tmp_path):
    (tmp_path / "app.py").write_text(
        "import os\nimport project_utils\nimport pandas as pd\nfrom sklearn.preprocessing import StandardScaler\nimport joblib\n",
        encoding="utf-8",
    )
    (tmp_path / "project_utils.py").write_text("VALUE = 1\n", encoding="utf-8")

    result = inspect_python_project(str(tmp_path))

    assert result["dependency_manifests"] == []
    assert result["imported_modules"] == ["joblib", "os", "pandas", "project_utils", "sklearn"]
    assert result["inferred_dependencies"] == ["joblib", "pandas", "scikit-learn"]
    assert result["unresolved_imports"] == []


def test_extracts_imports_from_fenced_python_but_keeps_syntax_diagnostic(tmp_path):
    (tmp_path / "wrapped.py").write_text(
        "```python\nimport pandas\nfrom sklearn.model_selection import train_test_split\n```\n",
        encoding="utf-8",
    )

    result = inspect_python_project(str(tmp_path))

    assert result["issues"][0]["kind"] == "syntax"
    assert result["inferred_dependencies"] == ["pandas", "scikit-learn"]
    assert result["unresolved_import_files"] == []