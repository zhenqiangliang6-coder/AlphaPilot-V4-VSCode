"""Read a small, allowlisted project context for mentor responses."""

import ast
import builtins
import importlib.metadata
import io
import re
import os
import sys
import tabnanny
import tokenize
from pathlib import Path

MAX_FILE_BYTES = 16_000
MAX_TOTAL_CHARS = 60_000
MAX_FILES_PER_GROUP = 6
MAX_REQUESTED_FILES = 5
MAX_PYTHON_FILES = 500
MAX_FIX_FILES = 10
MAX_FIX_CONTEXT_CHARS = 48_000
ABSOLUTE_SOURCE_PATH_PATTERN = re.compile(
    r'(?<![A-Za-z0-9_.-])[A-Za-z]:[\\/](?:[^<>:"|?*\r\n]+[\\/])*[^<>:"|?*\r\n]+\.py',
    re.IGNORECASE,
)
RELATIVE_SOURCE_PATH_PATTERN = re.compile(
    r"(?<![\w./\\-])(?:[\w.-]+[\\/])+[\w.-]+\.py",
    re.IGNORECASE,
)
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"}
_INSPECT_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".java", ".kt", ".kts",
    ".cpp", ".c", ".h", ".hpp", ".cc", ".cxx",
    ".rs", ".go",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".md", ".mdx", ".rst",
    ".html", ".css", ".scss", ".less",
    ".dockerfile", "Dockerfile",
    ".sh", ".bash", ".ps1", ".bat", ".cmd",
    ".env", ".env.example",
}
_PYTHON_ONLY_SYNTAX = {".py"}
IMPORT_TO_DISTRIBUTION = {
    "PIL": "Pillow",
    "OpenSSL": "pyOpenSSL",
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
    "fitz": "PyMuPDF",
    "googleapiclient": "google-api-python-client",
    "jwt": "PyJWT",
    "psycopg2": "psycopg2-binary",
    "serial": "pyserial",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "Crypto": "pycryptodome",
    "docx": "python-docx",
    "win32com": "pywin32",
}
KNOWN_DISTRIBUTIONS = {
    "beautifulsoup4",
    "flask",
    "joblib",
    "matplotlib",
    "numpy",
    "pandas",
    "pytest",
    "redis",
    "requests",
    "scipy",
    "sqlalchemy",
    "torch",
    "transformers",
    "urllib3",
}


def inspect_python_project(workspace_path):
    """Read and syntax-check project files across all supported languages, retaining bounded source for repair."""
    if not isinstance(workspace_path, str) or not workspace_path.strip():
        raise ValueError("工作区路径未设置，无法读取项目文件。")

    try:
        root = Path(workspace_path).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError(f"工作区路径不可访问: {workspace_path}") from error
    if not root.is_dir():
        raise ValueError(f"工作区路径不是目录: {workspace_path}")

    all_paths = []
    python_paths = []
    language_counts = {}
    walk_errors = []

    def record_walk_error(error):
        walk_errors.append(str(error))

    for directory, subdirectories, filenames in os.walk(root, onerror=record_walk_error):
        subdirectories[:] = sorted(
            name for name in subdirectories
            if name not in SKIP_DIRS and not name.startswith(".")
        )
        for filename in sorted(filenames):
            lower_name = filename.lower()
            is_match = lower_name.endswith(".py") or lower_name in _INSPECT_EXTENSIONS
            if not is_match:
                for ext in _INSPECT_EXTENSIONS:
                    if ext.startswith(".") and lower_name.endswith(ext):
                        is_match = True
                        break
            if not is_match:
                continue

            file_path = Path(directory) / filename
            all_paths.append(file_path)

            ext = file_path.suffix.lower() or (filename if filename.startswith(".") else f".{filename}")
            language_counts[ext] = language_counts.get(ext, 0) + 1

            if lower_name.endswith(".py"):
                python_paths.append(file_path)

            if len(all_paths) >= MAX_PYTHON_FILES:
                break
        if len(all_paths) >= MAX_PYTHON_FILES:
            break

    issues = []
    fix_sources = {}
    fix_context_size = 0
    fixable_issues = 0
    imported_modules = set()
    local_modules = {
        path.stem
        for path in python_paths
        if path.stem != "__init__"
    }
    local_modules.update(
        path.parent.name
        for path in python_paths
        if path.name == "__init__.py"
    )
    unresolved_import_files = []

    for path in python_paths:
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
            if not resolved.is_file():
                continue
            if resolved.stat().st_size > 1_000_000:
                issues.append({
                    "path": resolved.relative_to(root).as_posix(),
                    "kind": "skipped_large_file",
                    "message": "文件超过 1 MB 安全扫描上限。",
                })
                continue
            with tokenize.open(str(resolved)) as source_file:
                source = source_file.read()
        except (OSError, RuntimeError, UnicodeError, ValueError) as error:
            issues.append({
                "path": path.relative_to(root).as_posix(),
                "kind": "read_error",
                "message": str(error),
            })
            continue

        relative_path = resolved.relative_to(root).as_posix()
        import_source = _unwrap_python_fence(source)
        try:
            imported_modules.update(_imports_from_source(import_source))
        except SyntaxError:
            unresolved_import_files.append(relative_path)

        file_issue = None
        try:
            compile(source, relative_path, "exec")
        except (SyntaxError, IndentationError) as error:
            file_issue = {
                "path": relative_path,
                "kind": "indentation" if isinstance(error, IndentationError) else "syntax",
                "line": error.lineno,
                "message": error.msg,
            }
        else:
            try:
                tokens = tokenize.generate_tokens(io.StringIO(source).readline)
                tabnanny.process_tokens(tokens)
            except tabnanny.NannyNag as error:
                file_issue = {
                    "path": relative_path,
                    "kind": "indentation",
                    "line": error.get_lineno(),
                    "message": str(error),
                }
            except (tokenize.TokenError, IndentationError) as error:
                file_issue = {
                    "path": relative_path,
                    "kind": "indentation",
                    "message": str(error),
                }

        if file_issue:
            issues.append(file_issue)
            fixable_issues += 1
            if (
                len(fix_sources) < MAX_FIX_FILES
                and fix_context_size + len(source) <= MAX_FIX_CONTEXT_CHARS
            ):
                fix_sources[relative_path] = source
                fix_context_size += len(source)

    manifests = [
        name for name in (
            "requirements.txt",
            "requirements-dev.txt",
            "pyproject.toml",
            "setup.py",
        )
        if (root / name).is_file()
    ]
    inferred_dependencies, unresolved_imports = _infer_dependencies(
        imported_modules,
        local_modules,
    )
    return {
        "root": str(root),
        "python_file_count": len(python_paths),
        "total_file_count": len(all_paths),
        "language_counts": language_counts,
        "file_limit_reached": len(all_paths) >= MAX_PYTHON_FILES,
        "issues": issues,
        "source_files": fix_sources,
        "unavailable_fix_files": max(0, fixable_issues - len(fix_sources)),
        "fixable_issue_count": fixable_issues,
        "dependency_manifests": manifests,
        "imported_modules": sorted(imported_modules),
        "inferred_dependencies": inferred_dependencies,
        "unresolved_imports": unresolved_imports,
        "unresolved_import_files": unresolved_import_files,
        "scan_errors": walk_errors,
    }


def _unwrap_python_fence(source):
    lines = source.splitlines()
    if len(lines) >= 3 and lines[0].strip().startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1])
    return source


def _imports_from_source(source):
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".", 1)[0])
    return imported


def _infer_dependencies(imported_modules, local_modules):
    standard_modules = getattr(sys, "stdlib_module_names", set())
    builtin_modules = set(vars(builtins))
    try:
        installed_distributions = importlib.metadata.packages_distributions()
    except (AttributeError, OSError, ValueError):
        installed_distributions = {}

    dependencies = set()
    unresolved = set()
    for module in imported_modules:
        if module in standard_modules or module in builtin_modules or module in local_modules:
            continue
        distribution = IMPORT_TO_DISTRIBUTION.get(module)
        if distribution:
            dependencies.add(distribution)
            continue
        if module.casefold() in KNOWN_DISTRIBUTIONS:
            dependencies.add(module)
            continue
        candidates = installed_distributions.get(module, [])
        if len(candidates) == 1:
            dependencies.add(candidates[0])
        elif candidates:
            unresolved.add(module)
        else:
            unresolved.add(module)
    return sorted(dependencies, key=str.casefold), sorted(unresolved, key=str.casefold)


def read_project_context(workspace_path):
    if not isinstance(workspace_path, str) or not workspace_path.strip():
        return "", []

    try:
        root = Path(workspace_path).resolve(strict=True)
    except (OSError, RuntimeError):
        return "", []
    if not root.is_dir():
        return "", []

    groups = [
        ("README", [*root.glob("README*"), *root.glob("readme*")]),
        ("tests", _matching_files(root / "tests", ("test_*.py", "*_test.py", "*.test.*", "*.spec.*"))),
        ("startup", _matching_files(root, ("*.ps1", "*.bat", "*.cmd", "*.sh", "docker-compose.y*", "Makefile"))),
    ]
    sections = []
    sources = []
    remaining = MAX_TOTAL_CHARS

    for label, candidates in groups:
        selected = 0
        for candidate in sorted(set(candidates), key=lambda item: str(item).lower()):
            if selected >= MAX_FILES_PER_GROUP or remaining <= 0:
                break
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(root)
                if not resolved.is_file() or resolved.stat().st_size > MAX_FILE_BYTES:
                    continue
                content = resolved.read_text(encoding="utf-8", errors="replace")[:remaining]
            except (OSError, RuntimeError, ValueError):
                continue
            if not content.strip():
                continue
            relative_path = resolved.relative_to(root).as_posix()
            sections.append(f"### {label}: {relative_path}\n{content}")
            sources.append(relative_path)
            remaining -= len(content)
            selected += 1

    return "\n\n".join(sections), sources


def read_requested_python_files(workspace_path, prompt):
    if not isinstance(workspace_path, str) or not workspace_path.strip():
        return {}
    if not isinstance(prompt, str) or not prompt.strip():
        return {}

    try:
        root = Path(workspace_path).resolve(strict=True)
    except (OSError, RuntimeError):
        return {}
    if not root.is_dir():
        return {}

    absolute_matches = list(ABSOLUTE_SOURCE_PATH_PATTERN.finditer(prompt))
    matched_spans = [match.span() for match in absolute_matches]
    relative_matches = [
        match for match in RELATIVE_SOURCE_PATH_PATTERN.finditer(prompt)
        if not any(match.start() < end and match.end() > start for start, end in matched_spans)
    ]

    source_files = {}
    for requested_path in [match.group(0) for match in absolute_matches + relative_matches]:
        relative = Path(requested_path.replace("\\", "/"))
        if ".." in relative.parts:
            continue

        if relative.is_absolute():
            candidates = [relative]
        else:
            candidates = [root / relative]

        if not relative.is_absolute() and len(relative.parts) == 1 and not candidates[0].exists():
            candidates = [
                path for path in root.rglob(relative.name)
                if not any(part in SKIP_DIRS for part in path.parts)
            ]
            if len(candidates) != 1:
                continue

        try:
            resolved = candidates[0].resolve(strict=True)
            resolved.relative_to(root)
            if not resolved.is_file() or resolved.suffix.lower() != ".py":
                continue
            if resolved.stat().st_size > MAX_FILE_BYTES:
                continue
            content = resolved.read_text(encoding="utf-8", errors="replace")
        except (OSError, RuntimeError, ValueError):
            continue

        source_files[resolved.relative_to(root).as_posix()] = content
        if len(source_files) >= MAX_REQUESTED_FILES:
            break

    return source_files


def _matching_files(directory, patterns):
    if not directory.is_dir():
        return []
    matches = []
    for pattern in patterns:
        matches.extend(
            path for path in directory.rglob(pattern)
            if not any(part in SKIP_DIRS for part in path.parts)
        )
    return matches