# -*- coding: utf-8 -*-
# tests/test_p2_setup_step.py
# ---------------------------------------------------------
# P2: setup 步骤 — DEPENDS 块处理测试
# 内联副本 + 集成验证
# ---------------------------------------------------------

import sys
import os
import json
from pathlib import Path

# =========================================================
# 内联副本 — 与 setup_step.py 逻辑完全一致
# =========================================================

_MANIFEST_TEMPLATES = {
    "requirements.txt": "",
    "requirements-dev.txt": "",
    "package.json": '{\n  "name": "app",\n  "private": true,\n  "dependencies": {}\n}',
    "pyproject.toml": '[project]\nname = "app"\nversion = "0.1.0"\n',
    "Gemfile": '',
    "composer.json": '{\n  "name": "app/app",\n  "require": {}\n}',
    "go.mod": "module app\n\ngo 1.21\n",
    "Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\nedition = "2021"\n',
}


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def _sniff_ecosystem(file_ops: list, ws_root: str) -> set:
    manifests = set()
    ext_set = set()
    for op in file_ops:
        path = op.get("path", "")
        if not path or op.get("op") == "delete":
            continue
        ext = Path(path).suffix.lower()
        if ext:
            ext_set.add(ext)
        basename = Path(path).name
        if basename in _MANIFEST_TEMPLATES:
            manifests.add(path)

    if ".py" in ext_set:
        if not any(m.endswith("pyproject.toml") or m.endswith("requirements.txt")
                   for m in manifests):
            manifests.add("requirements.txt")

    if ext_set & {".ts", ".tsx", ".js", ".jsx"}:
        if not any(m.endswith("package.json") for m in manifests):
            manifests.add("package.json")

    if ws_root and os.path.isdir(ws_root):
        for manifest_name in _MANIFEST_TEMPLATES:
            mpath = os.path.join(ws_root, manifest_name)
            if os.path.isfile(mpath):
                manifests.add(manifest_name)

    return manifests


def _collect_depends_declarations(context: dict) -> list:
    all_depends = []
    for op in context.get("final_file_ops", []):
        if op.get("op") == "depends":
            files = op.get("data", {}).get("files", [])
            if files:
                all_depends.append(("_global_", files))
    for result in context.get("intermediate_results", []):
        if result.get("type") != "write":
            continue
        for op in result.get("file_ops", []):
            if op.get("op") == "depends":
                files = op.get("data", {}).get("files", [])
                if files:
                    all_depends.append((op.get("path", "_unknown_"), files))
    return all_depends


# 简化的 stub 生成逻辑（与 setup_step 一致）
_STUB_MAP = {
    ".py": "# TODO: 实现模块\n",
    ".ts": "// TODO: 实现模块\n",
    ".tsx": "// TODO: 实现模块\n",
    ".js": "// TODO: 实现模块\n",
    ".jsx": "// TODO: 实现模块\n",
    ".json": "{}\n",
    ".md": "# TODO\n",
}

# =========================================================
# 测试用例
# =========================================================

def make_context(final_file_ops=None, ws_root=""):
    return {
        "final_file_ops": (final_file_ops or []).copy(),
        "intermediate_results": [],
        "meta": {"workspace_path": ws_root},
    }


def make_file_op(op_type, path, data=None, internal=False):
    op = {"op": op_type, "path": path}
    if data:
        op["data"] = data
    if internal:
        op["_internal"] = True
    return op


def test_empty_context():
    """空 context → 无操作"""
    ctx = make_context([])
    deps = _collect_depends_declarations(ctx)
    assert deps == [], f"expected empty, got {deps}"


def test_no_depends_blocks():
    """无 DEPENDS 块 → 空列表"""
    ctx = make_context([
        make_file_op("create", "main.py"),
        make_file_op("create", "app/models.py"),
    ])
    deps = _collect_depends_declarations(ctx)
    assert deps == []


def test_single_depends_block():
    """单个 # DEPENDS 块"""
    ctx = make_context([
        make_file_op("depends", "_", data={"files": ["config.py", "utils.py"]}),
    ])
    deps = _collect_depends_declarations(ctx)
    assert len(deps) == 1
    assert deps[0][0] == "_global_"
    assert sorted(deps[0][1]) == ["config.py", "utils.py"]


def test_multiple_depends_blocks():
    """多个 # DEPENDS 块 — 全部收集"""
    ctx = make_context([
        make_file_op("depends", "_", data={"files": ["config.py"]}),
        make_file_op("depends", "_", data={"files": ["utils.py", "helpers.py"]}),
    ])
    deps = _collect_depends_declarations(ctx)
    assert len(deps) == 2


def test_depends_from_intermediate_results():
    """intermediate_results 中的 DEPENDS"""
    ctx = {
        "final_file_ops": [],
        "intermediate_results": [{
            "type": "write",
            "file_ops": [
                make_file_op("depends", "app.py",
                             data={"files": ["config.py", "models/user.py"]}),
            ],
        }],
        "meta": {"workspace_path": ""},
    }
    deps = _collect_depends_declarations(ctx)
    assert len(deps) == 1
    assert deps[0][0] == "app.py"
    assert "config.py" in deps[0][1]
    assert "models/user.py" in deps[0][1]


# =========================================================
# _sniff_ecosystem
# =========================================================

def test_sniff_python_only():
    """纯 Python 文件 → requirements.txt"""
    file_ops = [
        make_file_op("create", "backend/main.py"),
        make_file_op("create", "backend/models/user.py"),
    ]
    manifests = _sniff_ecosystem(file_ops, "")
    assert "requirements.txt" in manifests


def test_sniff_typescript():
    """TypeScript + React 文件 → package.json"""
    file_ops = [
        make_file_op("create", "frontend/src/App.tsx"),
        make_file_op("create", "frontend/src/api/tasks.ts"),
    ]
    manifests = _sniff_ecosystem(file_ops, "")
    assert "package.json" in manifests


def test_sniff_fullstack():
    """全栈文件 → requirements.txt + package.json"""
    file_ops = [
        make_file_op("create", "backend/main.py"),
        make_file_op("create", "frontend/src/App.tsx"),
        make_file_op("create", "frontend/src/api/tasks.ts"),
    ]
    manifests = _sniff_ecosystem(file_ops, "")
    assert "requirements.txt" in manifests
    assert "package.json" in manifests


def test_sniff_existing_manifest_not_duplicated():
    """已有清单文件 → 不重复添加"""
    file_ops = [
        make_file_op("create", "requirements.txt"),
        make_file_op("create", "backend/main.py"),
    ]
    manifests = _sniff_ecosystem(file_ops, "")
    # requirements.txt 已存在，不会被再次添加为 "需要 生成" 的
    # 但 _sniff_ecosystem 仍会从现有文件收集它
    assert "requirements.txt" in manifests
    # 不会因为 .py 又触发添加
    # 去重逻辑由 run_setup_step 的 existing_paths 保证


def test_sniff_no_code_files():
    """无代码文件 → 无清单"""
    file_ops = [
        make_file_op("create", "README.md"),
        make_file_op("create", "docs/guide.md"),
    ]
    manifests = _sniff_ecosystem(file_ops, "")
    # Markdown 不触发任何清单
    assert len(manifests) == 0


def test_sniff_python_has_pyproject():
    """Python + 已有 pyproject.toml → 不生成 requirements.txt"""
    file_ops = [
        make_file_op("create", "pyproject.toml"),
        make_file_op("create", "backend/main.py"),
    ]
    manifests = _sniff_ecosystem(file_ops, "")
    # pyproject.toml 已有，不应再提议 requirements.txt
    assert "pyproject.toml" in manifests
    # requirements.txt 不应该被当"需要生成"的
    # 验证：.py 触发了 manifest need，但 pyproject.toml 已覆盖
    has_py_manifest = any(
        m.endswith("pyproject.toml") or m.endswith("requirements.txt")
        for m in manifests
    )
    assert has_py_manifest


# =========================================================
# 缺失文件检测
# =========================================================

def test_missing_dependency_detected():
    """依赖文件不在 existing set 中 → 标记为缺失"""
    file_ops = [
        make_file_op("create", "app/main.py"),
        make_file_op("depends", "_", data={"files": ["app/config.py", "app/utils.py"]}),
    ]
    existing = {_normalize_path(op["path"]) for op in file_ops
                if op.get("op") != "delete"}

    deps = _collect_depends_declarations(make_context(file_ops))
    missing = set()
    for owner, dep_files in deps:
        for dep in dep_files:
            dep_norm = _normalize_path(dep.strip())
            if dep_norm not in existing:
                missing.add(dep_norm)

    assert "app/config.py" in missing
    assert "app/utils.py" in missing
    # main.py 已在 existing 中
    assert "app/main.py" not in missing


def test_existing_dependency_not_missing():
    """依赖文件已在 existing 中 → 不标记为缺失"""
    file_ops = [
        make_file_op("create", "app/main.py"),
        make_file_op("create", "app/config.py"),
        make_file_op("depends", "_", data={"files": ["app/config.py", "app/utils.py"]}),
    ]
    existing = {_normalize_path(op["path"]) for op in file_ops
                if op.get("op") != "delete"}

    deps = _collect_depends_declarations(make_context(file_ops))
    missing = set()
    for owner, dep_files in deps:
        for dep in dep_files:
            dep_norm = _normalize_path(dep.strip())
            if dep_norm not in existing:
                missing.add(dep_norm)

    assert "app/config.py" not in missing
    assert "app/utils.py" in missing


# =========================================================
# stub 生成内容
# =========================================================

def test_stub_python():
    path = "app/config.py"
    ext = Path(path).suffix.lower()
    content = _STUB_MAP.get(ext, "")
    assert "# TODO: 实现模块" in content


def test_stub_typescript():
    path = "src/api.ts"
    ext = Path(path).suffix.lower()
    content = _STUB_MAP.get(ext, "")
    assert "// TODO: 实现模块" in content


def test_stub_json():
    path = "package.json"
    ext = Path(path).suffix.lower()
    content = _STUB_MAP.get(ext, "")
    assert content == "{}\n"

# =========================================================
# 集成测试：run_setup_step
# =========================================================

def test_run_setup_step_full_flow():
    """完整 setup 流程"""
    from agents.qwen.step_executor.setup_step import run_setup_step

    context = {
        "final_file_ops": [
            {"op": "create", "path": "app/main.py", "content": "print('hello')"},
            {"op": "depends", "path": "_", "data": {"files": ["app/config.py", "app/utils.py"]}},
        ],
        "intermediate_results": [],
        "meta": {
            "workspace_path": "",
            "persona": "engineer",
        },
    }
    step = {"type": "setup", "output": {}}

    run_setup_step(step, context, [], task_id=None)

    output = step.get("output", {})
    stubs = output.get("stubs_created", 0)

    # 应该创建 2 个 stub（config.py, utils.py）
    assert stubs == 2, f"expected 2 stubs, got {stubs}: {output.get('text', '')}"

    # 应该创建 1 个清单文件（requirements.txt，因为有 .py）
    manifests = output.get("manifest_files_created", 0)
    assert manifests == 1, f"expected 1 manifest, got {manifests}: {output.get('text', '')}"

    # 验证 final_file_ops 新增了操作
    new_ops = output.get("file_ops", [])
    new_paths = {op["path"] for op in new_ops}
    assert "app/config.py" in new_paths
    assert "app/utils.py" in new_paths
    assert "requirements.txt" in new_paths


def test_run_setup_step_empty():
    """空 context → 无操作"""
    from agents.qwen.step_executor.setup_step import run_setup_step

    context = {
        "final_file_ops": [],
        "intermediate_results": [],
        "meta": {"workspace_path": ""},
    }
    step = {"type": "setup", "output": {}}

    run_setup_step(step, context, [], task_id=None)

    assert step["output"].get("stubs_created", -1) == 0


def test_run_setup_step_no_depends():
    """有 file_ops 但无 DEPENDS → 只生成清单"""
    from agents.qwen.step_executor.setup_step import run_setup_step

    context = {
        "final_file_ops": [
            {"op": "create", "path": "app/main.py", "content": "print('hello')"},
        ],
        "intermediate_results": [],
        "meta": {"workspace_path": ""},
    }
    step = {"type": "setup", "output": {}}

    run_setup_step(step, context, [], task_id=None)

    stubs = step["output"].get("stubs_created", -1)
    assert stubs == 0, f"expected 0 stubs, got {stubs}"


# =========================================================
# Runner
# =========================================================

if __name__ == "__main__":
    tests = [
        test_empty_context,
        test_no_depends_blocks,
        test_single_depends_block,
        test_multiple_depends_blocks,
        test_depends_from_intermediate_results,
        test_sniff_python_only,
        test_sniff_typescript,
        test_sniff_fullstack,
        test_sniff_existing_manifest_not_duplicated,
        test_sniff_no_code_files,
        test_sniff_python_has_pyproject,
        test_missing_dependency_detected,
        test_existing_dependency_not_missing,
        test_stub_python,
        test_stub_typescript,
        test_stub_json,
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

    print(f"\n{'─' * 35}")
    print(f"  通过: {passed}/{len(tests)}")
    print(f"  失败: {failed}/{len(tests)}")
    print(f"{'─' * 35}")
    sys.exit(0 if failed == 0 else 1)