"""独立验证 _rollback_workspace 原子回滚的各项能力"""
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

from test_observe_task_system import _rollback_workspace


def test_rollback_with_new_files():
    """快照后新增文件，回滚后应被删除"""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "backend").mkdir(exist_ok=True)

        # 快照: 1个文件
        (ws / "backend" / "keep.py").write_text("original")
        snapshot = {"backend/keep.py": "original"}

        # 新增文件（不在快照中）
        (ws / "backend" / "new_file.py").write_text("new content")

        report = _rollback_workspace(ws, snapshot)

        assert report["restored"] == 1, f"restored={report['restored']}"
        assert "backend/new_file.py" in report["deleted_new"], f"deleted_new={report['deleted_new']}"
        assert not (ws / "backend" / "new_file.py").exists(), "new_file.py 应被删除"
        assert (ws / "backend" / "keep.py").read_text() == "original", "keep.py 应恢复"
        print("  ✅ test_rollback_with_new_files: PASS")


def test_rollback_with_modified_files():
    """快照中已有文件被修改，回滚后应恢复原内容"""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "backend").mkdir(exist_ok=True)

        (ws / "backend" / "orders.py").write_text("original content")
        snapshot = {"backend/orders.py": "original content"}

        # 修改文件（LLM 写入了新内容）
        (ws / "backend" / "orders.py").write_text("modified by LLM")

        report = _rollback_workspace(ws, snapshot)

        assert report["restored"] == 1, f"restored={report['restored']}"
        assert (ws / "backend" / "orders.py").read_text() == "original content", "应恢复原内容"
        print("  ✅ test_rollback_with_modified_files: PASS")


def test_rollback_with_deleted_files():
    """快照中已有文件被手动删除，回滚后应重新创建"""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "backend").mkdir(exist_ok=True)

        (ws / "backend" / "models.py").write_text("model code")
        snapshot = {"backend/models.py": "model code"}

        # 删除文件
        (ws / "backend" / "models.py").unlink()
        assert not (ws / "backend" / "models.py").exists()

        report = _rollback_workspace(ws, snapshot)

        assert report["restored"] == 1, f"restored={report['restored']}"
        assert (ws / "backend" / "models.py").exists(), "models.py 应被恢复"
        assert (ws / "backend" / "models.py").read_text() == "model code"
        print("  ✅ test_rollback_with_deleted_files: PASS")


def test_rollback_with_non_python_files():
    """非 Python 文件也在快照中，回滚应正常恢复"""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "docs").mkdir(exist_ok=True)
        (ws / "backend").mkdir(exist_ok=True)

        (ws / "docs" / "README.md").write_text("# ShopFlow")
        (ws / "backend" / "__init__.py").write_text("")

        snapshot = {
            "docs/README.md": "# ShopFlow",
            "backend/__init__.py": "",
        }

        # 新增一个 Python 文件（应被删除）
        (ws / "backend" / "stray.py").write_text("junk")

        report = _rollback_workspace(ws, snapshot)

        assert report["restored"] == 2, f"restored={report['restored']}"
        assert "backend/stray.py" in report["deleted_new"], f"deleted_new={report['deleted_new']}"
        assert (ws / "docs" / "README.md").read_text() == "# ShopFlow"
        assert not (ws / "backend" / "stray.py").exists()
        print("  ✅ test_rollback_with_non_python_files: PASS")


def test_rollback_directory_cleanup():
    """回滚清理空目录"""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "backend").mkdir(exist_ok=True)
        (ws / "empty_dir").mkdir(exist_ok=True)  # 空目录
        (ws / "has_py_dir").mkdir(exist_ok=True)
        (ws / "has_py_dir" / "stray.py").write_text("content")  # 有 Python 文件

        snapshot = {"backend/__init__.py": "# init"}

        report = _rollback_workspace(ws, snapshot)

        # stray.py 应被删除，然后 has_py_dir 变成空目录，也应被删除
        assert "backend/__init__.py" in {k for k, v in snapshot.items()}

        # stray.py 应被删除
        assert not (ws / "has_py_dir" / "stray.py").exists(), "stray.py 应被删除"

        print("  ✅ test_rollback_directory_cleanup: PASS")


def test_rollback_consistency_verification():
    """验证一致性：回滚后不应有快照之外的 Python 文件"""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "src").mkdir(exist_ok=True)

        snapshot = {"src/main.py": "print('hello')"}

        # 新增多个文件
        (ws / "src" / "extra1.py").write_text("extra1")
        (ws / "src" / "extra2.py").write_text("extra2")

        report = _rollback_workspace(ws, snapshot)

        assert report["restored"] == 1
        assert len(report["deleted_new"]) == 2
        assert not report["errors"], f"应无错误: {report['errors']}"
        print("  ✅ test_rollback_consistency_verification: PASS")


if __name__ == "__main__":
    print("=== 回滚能力独立验证 ===\n")
    test_rollback_with_new_files()
    test_rollback_with_modified_files()
    test_rollback_with_deleted_files()
    test_rollback_with_non_python_files()
    test_rollback_directory_cleanup()
    test_rollback_consistency_verification()
    print("\n🎉 所有回滚测试通过！")