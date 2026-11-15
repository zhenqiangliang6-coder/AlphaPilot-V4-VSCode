# -*- coding: utf-8 -*-
"""workspace_cleanup 回归契约。

锁死四类曾经真实发生过的故障：
  1. 递归删目录触发宿主批量删除保护 → SystemExit，测试第一步就死；
  2. .venv / .git / node_modules 被无差别删除；
  3. 不校验目标身份，环境变量指错就清空真实项目；
  4. 产物清单里的路径越界删除工作区外的文件。
"""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker.workspace_cleanup import (  # noqa: E402
    WorkspaceCleanupRefused,
    clean_generated_artifacts,
    clean_workspace_safely,
    mark_test_workspace,
    validate_workspace,
)


@pytest.fixture
def ws(tmp_path):
    d = tmp_path / "scratch_ws"
    d.mkdir()
    mark_test_workspace(d)
    return d


def test_protected_directories_are_never_touched(ws):
    (ws / ".venv" / "lib").mkdir(parents=True)
    (ws / ".venv" / "lib" / "dep.py").write_text("x = 1", encoding="utf-8")
    (ws / ".git").mkdir()
    (ws / ".git" / "config").write_text("repo", encoding="utf-8")
    (ws / "node_modules" / "a").mkdir(parents=True)
    (ws / "node_modules" / "a" / "index.js").write_text("x", encoding="utf-8")

    report = clean_workspace_safely(ws)

    assert (ws / ".venv" / "lib" / "dep.py").read_text(encoding="utf-8") == "x = 1"
    assert (ws / ".git" / "config").exists()
    assert (ws / "node_modules" / "a" / "index.js").exists()
    assert not report["errors"]


def test_generated_files_and_empty_dirs_are_removed(ws):
    (ws / "backend").mkdir()
    (ws / "backend" / "a.py").write_text("x = 1", encoding="utf-8")
    (ws / "docs").mkdir()
    (ws / "docs" / "design.md").write_text("design", encoding="utf-8")

    report = clean_workspace_safely(ws)

    assert not (ws / "backend" / "a.py").exists()
    assert not (ws / "docs" / "design.md").exists()
    assert "backend" in report["removed_dirs"]
    assert "docs" in report["removed_dirs"]


def test_bulk_files_do_not_trigger_systemexit(ws):
    """旧实现删到 50+ 文件时会被宿主保护直接杀死进程。"""
    big = ws / "generated"
    big.mkdir()
    for i in range(200):
        (big / f"f{i}.py").write_text("x", encoding="utf-8")

    report = clean_workspace_safely(ws)

    assert len(report["deleted_files"]) == 200
    assert not report["errors"]


def test_fail_closed_on_real_git_project(tmp_path):
    d = tmp_path / "real_project"
    d.mkdir()
    (d / ".git").mkdir()
    (d / "important.py").write_text("DO NOT DELETE", encoding="utf-8")

    with pytest.raises(WorkspaceCleanupRefused):
        clean_workspace_safely(d)

    assert (d / "important.py").read_text(encoding="utf-8") == "DO NOT DELETE"


def test_fail_closed_on_unknown_directory(tmp_path):
    d = tmp_path / "unknown_dir"
    d.mkdir()
    (d / "a.py").write_text("x", encoding="utf-8")

    with pytest.raises(WorkspaceCleanupRefused):
        clean_workspace_safely(d)
    assert (d / "a.py").exists()


def test_explicit_allow_roots_enables_cleanup(tmp_path):
    d = tmp_path / "unknown_dir_2"
    d.mkdir()
    (d / "a.py").write_text("x", encoding="utf-8")

    report = clean_workspace_safely(d, allow_roots=[tmp_path])

    assert not (d / "a.py").exists()
    assert report["errors"] == []


def test_default_test_workspace_name_is_allowed(tmp_path):
    d = tmp_path / "shopflow_ecommerce"
    d.mkdir()
    ok, _reason = validate_workspace(d)
    assert ok is True


def test_generated_only_manifest_blocks_path_traversal(ws):
    (ws / "keep.py").write_text("KEEP", encoding="utf-8")
    (ws / "gen.py").write_text("GEN", encoding="utf-8")
    outside = ws.parent / "outside.py"
    outside.write_text("OUTSIDE", encoding="utf-8")
    (ws / ".alphapilot_generated.mark").write_text(
        '["gen.py", "../outside.py"]', encoding="utf-8"
    )

    report = clean_generated_artifacts(ws)

    assert not (ws / "gen.py").exists()
    assert (ws / "keep.py").read_text(encoding="utf-8") == "KEEP"
    assert outside.read_text(encoding="utf-8") == "OUTSIDE"
    assert any("越界" in k for k in report["kept"])


def test_generated_only_without_manifest_deletes_nothing(ws):
    (ws / "user_code.py").write_text("KEEP", encoding="utf-8")

    report = clean_generated_artifacts(ws)

    assert report["deleted_files"] == []
    assert (ws / "user_code.py").exists()


def test_dry_run_does_not_modify_disk(ws):
    (ws / "a.py").write_text("x", encoding="utf-8")

    report = clean_workspace_safely(ws, dry_run=True)

    assert (ws / "a.py").exists()
    assert report["dry_run"] is True


def test_marker_survives_so_repeated_cleanup_still_works(ws):
    """标记被误删后，第二次清理会被 fail-closed 拒绝（曾经的隐患）。"""
    (ws / "a.py").write_text("x", encoding="utf-8")
    clean_workspace_safely(ws)

    assert (ws / ".alphapilot_test_workspace").exists()
    (ws / "b.py").write_text("x", encoding="utf-8")
    report2 = clean_workspace_safely(ws)

    assert not (ws / "b.py").exists()
    assert report2["deleted_files"] == ["b.py"]


def test_traversal_entry_does_not_delete_same_named_local_file(ws):
    """旧实现把 '../outside.py' 洗成 'outside.py'，会误删工作区内同名文件。"""
    (ws / "outside.py").write_text("LOCAL", encoding="utf-8")
    (ws / ".alphapilot_generated.mark").write_text(
        '["../outside.py"]', encoding="utf-8"
    )

    report = clean_generated_artifacts(ws)

    assert (ws / "outside.py").read_text(encoding="utf-8") == "LOCAL"
    assert report["deleted_files"] == []
    assert any("越界" in k for k in report["kept"])
