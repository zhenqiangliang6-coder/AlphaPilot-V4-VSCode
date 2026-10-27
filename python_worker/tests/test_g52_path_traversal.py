# -*- coding: utf-8 -*-
"""
G5.2 契约测试 — 路径穿越防护

测试 _is_safe_subpath 和 validate_workspace_evidence 的路径边界安全。

G5.2 规则：
  - 规范化后的证据文件路径必须位于工作区内
  - 防御向量：../ 遍历、绝对路径、符号链接、Windows 大小写/盘符语义
  - 越界路径必须被拒绝并标记为 skipped_entries
  - 合法工作区内文件通过所有验证后仍需通过 os.path.isfile 存在性检查
"""

import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from task_state_contract import (
    EvidenceGate,
    _is_safe_subpath,
    validate_workspace_evidence,
    EVIDENCE_STATUS_ACQUIRED,
    EVIDENCE_STATUS_FAILED,
    EVIDENCE_STATUS_NOT_REQUIRED,
)


# ═══════════════════════════════════════════════════════════════
# _is_safe_subpath 单元测试
# ═══════════════════════════════════════════════════════════════

class TestIsSafeSubpath:
    """_is_safe_subpath 纯函数测试"""

    def test_same_path_returns_true(self):
        assert _is_safe_subpath("/workspace", "file.py") is True

    def test_subdirectory_returns_true(self):
        assert _is_safe_subpath("/workspace", "subdir/file.py") is True

    def test_nested_subdirectory_returns_true(self):
        assert _is_safe_subpath("/workspace", "a/b/c/file.py") is True

    def test_dot_dot_traversal_blocked(self):
        assert _is_safe_subpath("/workspace", "../etc/passwd") is False

    def test_double_dot_dot_traversal_blocked(self):
        assert _is_safe_subpath("/workspace", "../../etc/passwd") is False

    def test_dot_dot_inside_subdir_blocked(self):
        assert _is_safe_subpath("/workspace", "subdir/../../../etc/passwd") is False

    def test_absolute_path_blocked(self):
        assert _is_safe_subpath("/workspace", "/etc/passwd") is False

    def test_absolute_path_with_drive_letter_blocked(self):
        assert _is_safe_subpath("C:\\workspace", "D:\\secret\\data.txt") is False

    def test_empty_workspace_returns_false(self):
        assert _is_safe_subpath("", "file.py") is False

    def test_empty_file_path_returns_false(self):
        assert _is_safe_subpath("/workspace", "") is False

    def test_empty_both_returns_false(self):
        assert _is_safe_subpath("", "") is False

    def test_dot_relative_returns_true(self):
        assert _is_safe_subpath("/workspace", "./file.py") is True

    def test_normalized_dot_dot_in_middle_blocked(self):
        assert _is_safe_subpath("/workspace", "subdir/../subdir2/file.py") is True

    def test_windows_backslash_separator(self):
        assert _is_safe_subpath("C:\\workspace", "subdir\\file.py") is True

    def test_windows_backslash_dot_dot_blocked(self):
        assert _is_safe_subpath("C:\\workspace", "..\\windows\\system32\\config") is False

    def test_case_insensitive_windows(self):
        result = _is_safe_subpath("C:\\WORKSPACE", "file.py")
        assert result is True


# ═══════════════════════════════════════════════════════════════
# validate_workspace_evidence 集成测试（使用临时工作区）
# ═══════════════════════════════════════════════════════════════

class TestValidateWorkspaceEvidenceWithRealFS:
    """使用真实临时目录验证 validate_workspace_evidence 的路径穿越防护"""

    @classmethod
    def setup_class(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="g52_test_")
        cls.ws_dir = os.path.join(cls.tmpdir, "workspace")
        os.makedirs(cls.ws_dir, exist_ok=True)

        cls.outside_dir = os.path.join(cls.tmpdir, "outside")
        os.makedirs(cls.outside_dir, exist_ok=True)

        cls.legit_file = os.path.join(cls.ws_dir, "legit.py")
        with open(cls.legit_file, "w") as f:
            f.write("# legit")

        cls.outside_file = os.path.join(cls.outside_dir, "secret.txt")
        with open(cls.outside_file, "w") as f:
            f.write("secret")

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_legit_file_in_workspace_passes(self):
        meta = {
            "workspace_evidence": {"legit.py": "content"},
            "workspace_path": self.ws_dir,
        }
        gate = validate_workspace_evidence(meta)
        assert gate.status == EVIDENCE_STATUS_ACQUIRED
        assert "legit.py" in gate.files_read

    def test_dot_dot_to_outside_blocked(self):
        meta = {
            "workspace_evidence": {"../outside/secret.txt": "content"},
            "workspace_path": self.ws_dir,
        }
        gate = validate_workspace_evidence(meta)
        assert gate.status == EVIDENCE_STATUS_FAILED
        assert gate.failure_reason

    def test_absolute_to_outside_blocked(self):
        meta = {
            "workspace_evidence": {self.outside_file: "content"},
            "workspace_path": self.ws_dir,
        }
        gate = validate_workspace_evidence(meta)
        assert gate.status == EVIDENCE_STATUS_FAILED
        assert gate.failure_reason

    def test_multiple_keys_one_legit_one_traversal(self):
        meta = {
            "workspace_evidence": {
                "legit.py": "content",
                "../outside/secret.txt": "bad",
            },
            "workspace_path": self.ws_dir,
        }
        gate = validate_workspace_evidence(meta)
        assert gate.status == EVIDENCE_STATUS_ACQUIRED
        assert "legit.py" in gate.files_read
        assert "../outside/secret.txt" not in gate.files_read

    def test_nonexistent_but_inside_workspace_fails_isfile(self):
        meta = {
            "workspace_evidence": {"ghost.py": "content"},
            "workspace_path": self.ws_dir,
        }
        gate = validate_workspace_evidence(meta)
        assert gate.status == EVIDENCE_STATUS_FAILED

    def test_empty_evidence_fails(self):
        meta = {
            "workspace_evidence": {},
            "workspace_path": self.ws_dir,
        }
        gate = validate_workspace_evidence(meta)
        assert gate.status == EVIDENCE_STATUS_FAILED

    def test_empty_string_values_skipped(self):
        meta = {
            "workspace_evidence": {"legit.py": ""},
            "workspace_path": self.ws_dir,
        }
        gate = validate_workspace_evidence(meta)
        assert gate.status == EVIDENCE_STATUS_FAILED

    def test_no_workspace_path_still_validates_content(self):
        meta = {
            "workspace_evidence": {"legit.py": "content"},
            "workspace_path": "",
        }
        gate = validate_workspace_evidence(meta)
        assert gate.status == EVIDENCE_STATUS_ACQUIRED