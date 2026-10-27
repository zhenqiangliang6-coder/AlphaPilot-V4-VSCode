"""Shared configuration, imports, and utility functions for smoke tests."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from python_worker.worker_config import DASHSCOPE_API_KEY  # noqa: E402

TEST_IMPORT_DIV = (
    "import sys\nfrom pathlib import Path\n"
    "sys.path.insert(0, str(Path(__file__).resolve().parent.parent))\n"
)


def apply_file_ops(sandbox: Path, file_ops: list[dict]) -> None:
    root = sandbox.resolve()
    for operation in file_ops:
        relative = Path(operation["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise AssertionError(f"Unsafe sandbox path: {relative}")
        target = (root / relative).resolve()
        target.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(operation.get("content", ""), encoding="utf-8")


def run_pytest(sandbox: Path) -> subprocess.CompletedProcess[str] | None:
    if importlib.util.find_spec("pytest") is None:
        return None
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=sandbox,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env=env,
        check=False,
    )


def run_pytest_inline(workspace: Path, test_file_rel: str) -> tuple[bool, str, str]:
    command = [
        sys.executable, "-m", "pytest",
        str(workspace / test_file_rel), "-q", "--tb=short",
    ]
    result = subprocess.run(
        command, cwd=str(workspace),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, check=False,
    )
    return result.returncode == 0, result.stdout or "", result.stderr or ""