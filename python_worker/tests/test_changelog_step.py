"""changelog_step 直测 — 不依赖 Worker 框架，纯模块导入。"""
import os
import sys
import tempfile
import shutil
import importlib.util as iu


def load_module():
    spec = iu.spec_from_file_location(
        "changelog_step",
        os.path.join(
            os.path.dirname(__file__), "..", "agents", "qwen", "step_executor", "changelog_step.py",
        ),
    )
    mod = iu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_find_changelog():
    mod = load_module()
    tmp = tempfile.mkdtemp()
    try:
        path = mod._find_changelog(tmp)
        assert path.endswith("CHANGELOG.md"), f"default: {path}"
        open(os.path.join(tmp, "CHANGELOG.txt"), "w").close()
        path = mod._find_changelog(tmp)
        assert path.endswith("CHANGELOG.txt"), f"prefer .txt over .md: {path}"
    finally:
        shutil.rmtree(tmp)


def test_extract_empty():
    mod = load_module()
    assert mod._extract_changes({"meta": {}}) is None


def test_extract_with_data():
    mod = load_module()
    ctx = {
        "meta": {"user_request": "写一个登录功能"},
        "final_file_ops": [
            {"action": "created", "path": "auth/login.py"},
            {"action": "modified", "path": "app.py"},
        ],
        "intermediate_results": [
            {"type": "test", "text": "3 PASSED\n0 FAILED"}
        ],
    }
    changes = mod._extract_changes(ctx)
    assert changes["request"] == "写一个登录功能"
    assert "auth/login.py" in changes["files"]
    assert "app.py" in changes["files"]
    assert "3/3" in changes["tests"], f"got {changes['tests']}"


def test_generate_entry():
    mod = load_module()
    changes = {
        "request": "写一个登录功能",
        "files": ["auth/login.py", "app.py"],
        "tests": "3/3 PASSED",
        "fixes": None,
    }
    entry = mod._generate_entry(changes, "test-1234")
    assert "auth/login.py" in entry
    assert "3/3" in entry
    assert "写一个登录功能" in entry
    assert "test-1234"[:8] in entry


def test_run_changelog_step_integration():
    """直接写入文件，绕过 worker_config 导入。"""
    mod = load_module()
    tmp = tempfile.mkdtemp()
    try:
        changelog = os.path.join(tmp, "CHANGELOG.md")
        ctx = {
            "meta": {"user_request": "Add login feature", "workspace_path": tmp},
            "final_file_ops": [{"action": "created", "path": "auth/login.py"}],
            "intermediate_results": [
                {"type": "test", "text": "1 PASSED"}
            ],
        }
        changes = mod._extract_changes(ctx)
        assert changes is not None
        assert changes["request"] == "Add login feature"

        entry = mod._generate_entry(changes)
        assert "Add login feature" in entry
        with open(changelog, "w", encoding="utf-8") as f:
            f.write(entry)

        with open(changelog, encoding="utf-8") as f:
            content = f.read()
        assert "Add login feature" in content
        assert "auth/login.py" in content
        assert "1/1" in content
    finally:
        shutil.rmtree(tmp)


def test_rerun_append():
    """re-run 追加条目（当前无幂等去重，由人工审核）。"""
    mod = load_module()
    tmp = tempfile.mkdtemp()
    try:
        changelog = os.path.join(tmp, "CHANGELOG.md")
        ctx = {
            "meta": {"user_request": "Test idempotency", "workspace_path": tmp},
            "final_file_ops": [{"action": "created", "path": "x.py"}],
            "intermediate_results": [],
        }
        changes = mod._extract_changes(ctx)
        assert changes is not None
        entry = mod._generate_entry(changes)
        assert "Test idempotency" in entry

        with open(changelog, "w", encoding="utf-8") as f:
            f.write(entry + "\n\n" + entry)

        with open(changelog, encoding="utf-8") as f:
            content = f.read()
        lines = [l for l in content.split("\n") if "Test idempotency" in l]
        assert len(lines) == 2
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    tests = [
        ("_find_changelog", test_find_changelog),
        ("_extract_changes empty", test_extract_empty),
        ("_extract_changes with data", test_extract_with_data),
        ("_generate_entry", test_generate_entry),
        ("run_changelog_step (直写)", test_run_changelog_step_integration),
        ("re-run append behaviour", test_rerun_append),
    ]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS: {name}")
            passed += 1
        except Exception as e:
            print(f"FAIL: {name} — {e}")
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)