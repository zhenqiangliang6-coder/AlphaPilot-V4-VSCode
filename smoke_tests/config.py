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

# ═════════════════════════════════════════════════════════════════
# Runtime discovery — portable runtime env support
# ═════════════════════════════════════════════════════════════════
_RUNTIME_ROOT = SCRIPT_DIR / "runtime"


def find_runtime_jdk() -> str | None:
    """Discover JDK from runtime/ dir, VS Code extensions, or JAVA_HOME."""
    candidates = [
        (_RUNTIME_ROOT / "java" / "jdk-17" / "bin" / "javac.exe"),
        (_RUNTIME_ROOT / "java" / "jdk-17" / "bin" / "java.exe"),
    ]
    for p in candidates:
        if p.is_file():
            return str(p.parent.parent)

    # VS Code Java extension bundled JDK
    vscode_ext = Path.home() / ".vscode" / "extensions"
    if vscode_ext.exists():
        for java_ext in sorted(vscode_ext.glob("redhat.java-*"), reverse=True):
            for jre_dir in sorted(java_ext.glob("jre/*"), reverse=True):
                javac = jre_dir / "bin" / "javac.exe"
                if javac.is_file():
                    return str(jre_dir)

    env_home = os.environ.get("JAVA_HOME", "")
    if env_home and (Path(env_home) / "bin" / "java.exe").is_file():
        return env_home
    return None


def find_runtime_maven() -> str | None:
    candidates = [
        (_RUNTIME_ROOT / "maven" / "apache-maven-3.9" / "bin" / "mvn.cmd"),
    ]
    for p in candidates:
        if p.is_file():
            return str(p.parent.parent)
    env_home = os.environ.get("MAVEN_HOME", "") or os.environ.get("M2_HOME", "")
    if env_home and (Path(env_home) / "bin" / "mvn.cmd").is_file():
        return env_home
    return None


def is_java_runtime_ready() -> bool:
    return find_runtime_jdk() is not None and find_runtime_maven() is not None


def is_node_runtime_ready() -> bool:
    import shutil
    return shutil.which("node") is not None


def runtime_report() -> dict[str, bool]:
    return {
        "python": True,
        "nodejs": is_node_runtime_ready(),
        "java": is_java_runtime_ready(),
        "jdk": find_runtime_jdk() is not None,
        "maven": find_runtime_maven() is not None,
    }


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