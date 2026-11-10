# -*- coding: utf-8 -*-
# tests/test_p0_package_inits.py
# ---------------------------------------------------------
# P0: Python 包完整性 — __init__.py 自动补充测试
#
# 测试 _ensure_python_package_inits 的确定性后处理逻辑
# ---------------------------------------------------------

import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_file_op_mock(action, path, content="", file_type="file", language=None,
                        reason="", from_step="", intent="", data=None):
    op = {
        "op": action,
        "path": path,
        "content": content,
        "file_type": file_type,
        "language": language,
        "reason": reason,
        "from_step": from_step,
        "intent": intent,
    }
    if data:
        op["data"] = data
    return op


def _ensure_python_package_inits(file_ops: list) -> int:
    """（测试用副本 — 与 step_runner.py 逻辑完全一致）"""
    create_ops = [
        op for op in file_ops
        if op.get("op") in ("create", "modify")
    ]
    if not create_ops:
        return 0

    existing_paths = {
        op["path"] for op in file_ops
        if op.get("path") and op.get("op") != "delete"
    }

    init_paths_needed = set()
    for op in create_ops:
        path = op.get("path", "")
        if not path.endswith(".py"):
            continue
        parts = Path(path).parent.parts
        for i in range(1, len(parts) + 1):
            pkg_path = str(Path(*parts[:i]) / "__init__.py").replace("\\", "/")
            if pkg_path != path and pkg_path not in existing_paths:
                init_paths_needed.add(pkg_path)

    count = 0
    for init_path in sorted(init_paths_needed):
        file_ops.append(create_file_op_mock(
            action="create",
            path=init_path,
            content="",
            file_type="file",
            language="python",
            reason="Python 包初始化文件（AlphaPilot 自动补充）",
            from_step="workspace",
        ))
        existing_paths.add(init_path)
        count += 1

    return count


# =========================================================
# Test Cases
# =========================================================


def test_empty_file_ops():
    """空 file_ops → 返回 0"""
    ops = []
    assert _ensure_python_package_inits(ops) == 0
    assert len(ops) == 0


def test_no_python_files():
    """只有前端文件 → 不生成 __init__.py"""
    ops = [
        create_file_op_mock("create", "src/App.tsx"),
        create_file_op_mock("create", "src/api/tasks.ts"),
    ]
    assert _ensure_python_package_inits(ops) == 0
    assert len(ops) == 2


def test_single_py_root_level():
    """根级别 main.py → 不需要 __init__.py（根目录不是包）"""
    ops = [create_file_op_mock("create", "main.py")]
    assert _ensure_python_package_inits(ops) == 0
    assert len(ops) == 1


def test_py_in_package():
    """backend/models/task.py → 需要 backend/__init__.py 和 backend/models/__init__.py"""
    ops = [
        create_file_op_mock("create", "backend/models/task.py"),
    ]
    count = _ensure_python_package_inits(ops)
    assert count == 2
    paths = {op["path"] for op in ops}
    assert "backend/__init__.py" in paths
    assert "backend/models/__init__.py" in paths
    assert len(ops) == 3  # 1 original + 2 inits


def test_init_already_exists():
    """已有 __init__.py → 不重复创建"""
    ops = [
        create_file_op_mock("create", "backend/models/task.py"),
        create_file_op_mock("create", "backend/__init__.py"),
    ]
    count = _ensure_python_package_inits(ops)
    assert count == 1  # 只有 backend/models/__init__.py
    paths = {op["path"] for op in ops}
    assert "backend/models/__init__.py" in paths
    assert len(ops) == 3


def test_deeply_nested():
    """深度嵌套目录 — 所有中间级自动补充"""
    ops = [
        create_file_op_mock("create", "src/services/domain/auth/handler.py"),
    ]
    count = _ensure_python_package_inits(ops)
    assert count == 4, f"expected 4, got {count}"
    paths = {op["path"] for op in ops}
    assert "src/__init__.py" in paths
    assert "src/services/__init__.py" in paths
    assert "src/services/domain/__init__.py" in paths
    assert "src/services/domain/auth/__init__.py" in paths
    assert len(ops) == 5  # 1 original + 4 inits


def test_mixed_frontend_backend():
    """混合前后端项目 — 只有 Python 包需要 __init__.py"""
    ops = [
        create_file_op_mock("create", "backend/main.py"),
        create_file_op_mock("create", "backend/routers/tasks.py"),
        create_file_op_mock("create", "frontend/src/App.tsx"),
        create_file_op_mock("create", "frontend/src/components/TaskList.tsx"),
        create_file_op_mock("create", "backend/models/__init__.py"),
    ]
    count = _ensure_python_package_inits(ops)
    # backend/__init__.py, backend/routers/__init__.py
    # (backend/models/__init__.py already exists)
    assert count == 2
    paths = {op["path"] for op in ops}
    assert "backend/__init__.py" in paths
    assert "backend/routers/__init__.py" in paths
    # 前端文件不应有 __init__.py
    assert "frontend/__init__.py" not in paths
    assert "frontend/src/__init__.py" not in paths
    assert len(ops) == 7  # 5 original + 2 inits


def test_delete_ops_ignored():
    """delete 操作不触发 __init__.py 创建"""
    ops = [
        create_file_op_mock("create", "backend/main.py"),
        create_file_op_mock("delete", "backend/old_file.py"),
    ]
    count = _ensure_python_package_inits(ops)
    assert count == 1  # 只有 backend/__init__.py
    paths = {op["path"] for op in ops}
    assert "backend/__init__.py" in paths


def test_test_files():
    """tests/ 目录也需要 __init__.py"""
    ops = [
        create_file_op_mock("create", "tests/test_tasks.py"),
        create_file_op_mock("create", "tests/test_users.py"),
    ]
    count = _ensure_python_package_inits(ops)
    assert count == 1
    paths = {op["path"] for op in ops}
    assert "tests/__init__.py" in paths
    assert len(ops) == 3


# =========================================================
# Runner
# =========================================================

if __name__ == "__main__":
    tests = [
        test_empty_file_ops,
        test_no_python_files,
        test_single_py_root_level,
        test_py_in_package,
        test_init_already_exists,
        test_deeply_nested,
        test_mixed_frontend_backend,
        test_delete_ops_ignored,
        test_test_files,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {test.__name__}: {e}")
            failed += 1

    print(f"\n─────────────────────────────")
    print(f"  通过: {passed}/{len(tests)}")
    print(f"  失败: {failed}/{len(tests)}")
    print(f"─────────────────────────────")
    sys.exit(0 if failed == 0 else 1)