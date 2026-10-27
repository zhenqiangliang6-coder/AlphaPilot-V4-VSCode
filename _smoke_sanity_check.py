"""冒烟测试前的手动验证：确保自愈逻辑的核心场景正确。"""
import sys
import subprocess
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

BUGGY = "def div(a, b):\n    return a / b\n"
FIXED = (
    "def div(a, b):\n"
    "    if b == 0:\n"
    "        raise ValueError('division by zero')\n"
    "    return a / b\n"
)
UNFIXABLE = "def broken():\n    return undefined_var\n"

TEST_PASSING = (
    "import sys\nfrom pathlib import Path\n"
    "sys.path.insert(0, str(Path(__file__).resolve().parent.parent))\n"
    "from src.calc import div\nimport pytest\n"
    "def test_div():\n    assert div(10, 2) == 5\n"
    "def test_div_zero():\n"
    "    with pytest.raises(ValueError):\n        div(1, 0)\n"
)
TEST_UNFIXABLE = (
    "import sys\nfrom pathlib import Path\n"
    "sys.path.insert(0, str(Path(__file__).resolve().parent.parent))\n"
    "from src.broken_mod import broken\n"
    "def test_broken():\n    assert broken() is not None\n"
)


def run_pytest(sandbox, test_name, test_content):
    test_file = sandbox / "tests" / test_name
    test_file.write_text(test_content, encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-q", "--tb=short"],
        cwd=str(sandbox), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30, check=False,
    )
    return r.returncode == 0, r.stdout, r.stderr


def main():
    with tempfile.TemporaryDirectory(prefix="smoke_heal_check_") as td:
        s = Path(td)
        (s / "src").mkdir()
        (s / "tests").mkdir()

        all_ok = True

        # ── 成功路径：buggy → FAIL → fixed → PASS ──
        (s / "src" / "calc.py").write_text(BUGGY, encoding="utf-8")
        passed, out, err = run_pytest(s, "test_success_1.py", TEST_PASSING)
        ok = not passed
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
            print(f"  [{status}] 初始测试应失败但通过了")
            print(f"  stdout: {out[:200]}")

        (s / "src" / "calc.py").write_text(FIXED, encoding="utf-8")
        passed, out, err = run_pytest(s, "test_success_1.py", TEST_PASSING)
        ok2 = passed
        status2 = "PASS" if ok2 else "FAIL"
        if not ok2:
            all_ok = False
            print(f"  [{status2}] 修复后测试应通过但失败了")
            print(f"  stdout: {out[:200]}")
            print(f"  stderr: {err[:200]}")

        print(f"  [{'PASS' if ok else 'FAIL'}] 成功路径-初始失败: {'✓' if ok else '✗'}")
        print(f"  [{'PASS' if ok2 else 'FAIL'}] 成功路径-修复通过: {'✓' if ok2 else '✗'}")

        # ── 失败路径：永远修不好 ──
        (s / "src" / "broken_mod.py").write_text(UNFIXABLE, encoding="utf-8")
        passed, out, err = run_pytest(s, "test_fail_1.py", TEST_UNFIXABLE)
        ok3 = not passed
        if not ok3:
            all_ok = False

        print(f"  [{'PASS' if ok3 else 'FAIL'}] 失败路径-始终失败: {'✓' if ok3 else '✗'}")

    if all_ok:
        print("\n✅ 所有核心场景验证通过，可以运行完整冒烟测试")
    else:
        print("\n❌ 部分场景失败")
        sys.exit(1)


if __name__ == "__main__":
    main()