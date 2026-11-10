"""Capability: Direct code line counting — runs in-process, returns numbers, not tools.

This capability REPLACES the old behavior of generating a code_counter.py script.
It directly counts lines using a Python-native scanner (no external cloc dependency needed,
but cloc is used as a fast path when available).
"""

import os
import json
import subprocess
from dataclasses import dataclass, field
from collections import defaultdict


LANGUAGE_EXTENSIONS = {
    ".py": "Python",
    ".pyx": "Cython",
    ".js": "JavaScript",
    ".jsx": "JavaScript (JSX)",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (TSX)",
    ".mjs": "JavaScript (ESM)",
    ".cjs": "JavaScript (CJS)",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".less": "Less",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".xml": "XML",
    ".md": "Markdown",
    ".mdx": "MDX",
    ".rst": "reStructuredText",
    ".txt": "Text",
    ".toml": "TOML",
    ".cfg": "Config",
    ".ini": "Config",
    ".env": "Environment",
    ".sh": "Shell",
    ".bash": "Bash",
    ".zsh": "Zsh",
    ".bat": "Batch",
    ".ps1": "PowerShell",
    ".java": "Java",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".go": "Go",
    ".rs": "Rust",
    ".c": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".h": "C/C++ Header",
    ".hpp": "C++ Header",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".r": "R",
    ".sql": "SQL",
    ".graphql": "GraphQL",
    ".proto": "Protobuf",
    ".dockerfile": "Dockerfile",
    ".makefile": "Makefile",
    ".cmake": "CMake",
}

SKIP_DIRS = frozenset({
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    ".next", "dist", "build", ".cache", ".idea", ".vscode",
    "target", ".mypy_cache", ".pytest_cache", ".tox",
    ".eggs", "*.egg-info",
})

SKIP_FILES = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Pipfile.lock", "Cargo.lock",
    "uv.lock",
})


@dataclass
class CodeStats:
    total_lines: int = 0
    total_files: int = 0
    total_blank_lines: int = 0
    total_comment_lines: int = 0
    by_language: dict = field(default_factory=lambda: defaultdict(dict))
    largest_files: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_lines": self.total_lines,
            "total_files": self.total_files,
            "total_blank_lines": self.total_blank_lines,
            "total_comment_lines": self.total_comment_lines,
            "by_language": dict(self.by_language),
            "largest_files": self.largest_files[:10],
        }

    def format_for_user(self) -> str:
        if self.total_lines == 0:
            return "项目统计：未找到可统计的代码文件。"

        lines = []
        lines.append("## 项目代码统计")
        lines.append("")
        lines.append(f"| 指标 | 数值 |")
        lines.append(f"|------|------|")
        lines.append(f"| **总行数** | **{self.total_lines:,}** |")
        lines.append(f"| **总文件数** | **{self.total_files}** |")
        lines.append(f"| 空行 | {self.total_blank_lines:,} |")
        lines.append(f"| 注释行 | {self.total_comment_lines:,} |")
        lines.append(f"| 实际代码行 | {self.total_lines - self.total_blank_lines - self.total_comment_lines:,} |")
        lines.append("")

        if self.by_language:
            lines.append("### 按语言分布")
            lines.append("")
            lines.append("| 语言 | 文件数 | 总行数 |")
            lines.append("|------|--------|--------|")
            sorted_langs = sorted(
                self.by_language.items(),
                key=lambda x: x[1].get("lines", 0), reverse=True
            )
            for lang, stats in sorted_langs:
                lines.append(f"| {lang} | {stats.get('files', 0)} | {stats.get('lines', 0):,} |")

        if self.largest_files:
            lines.append("")
            lines.append("### 最大的源文件")
            lines.append("")
            lines.append("| 文件 | 行数 | 语言 |")
            lines.append("|------|------|------|")
            for f in self.largest_files[:10]:
                lines.append(f"| {f['path']} | {f['lines']:,} | {f['language']} |")

        return "\n".join(lines)


def _is_comment_line(line: str, ext: str) -> bool:
    """Detect if a line is a comment line based on file extension."""
    stripped = line.strip()

    if ext in (".py", ".pyx", ".rb", ".sh", ".bash", ".zsh", ".r", ".yml", ".yaml",
                ".toml", ".cfg", ".ini", ".dockerfile", ".makefile", ".cmake"):
        return stripped.startswith("#")

    if ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".kt",
                ".scala", ".go", ".rs", ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp",
                ".cs", ".swift", ".php", ".proto", ".sql"):
        if stripped.startswith("//"):
            return True
        if stripped.startswith("/*"):
            return True
        if stripped.startswith("*") and not stripped.startswith("**/"):
            return True
        return False

    if ext in (".css", ".scss", ".less"):
        return stripped.startswith("/*") or stripped.startswith("*")

    if ext in (".html", ".vue", ".svelte", ".xml", ".mdx"):
        return stripped.startswith("<!--")

    return False


def _count_file_lines(filepath: str, ext: str) -> dict:
    """Count lines in a single file. Returns {lines, blank, comments}."""
    result = {"lines": 0, "blank": 0, "comments": 0}
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                result["lines"] += 1
                if line.strip() == "":
                    result["blank"] += 1
                elif _is_comment_line(line, ext):
                    result["comments"] += 1
    except (IOError, OSError, UnicodeDecodeError):
        result["lines"] = 0
    return result


def _try_cloc(workspace_path: str) -> CodeStats:
    """Try using cloc (fast path). Returns None if cloc is not available."""
    try:
        proc = subprocess.run(
            ["cloc", "--json", "--quiet", "--exclude-dir",
             ",".join(SKIP_DIRS), workspace_path],
            capture_output=True, text=True, timeout=60
        )
        if proc.returncode != 0:
            return None
        data = json.loads(proc.stdout)
        stats = CodeStats()
        total = data.get("SUM", {})
        stats.total_lines = total.get("code", 0) + total.get("blank", 0) + total.get("comment", 0)
        stats.total_blank_lines = total.get("blank", 0)
        stats.total_comment_lines = total.get("comment", 0)
        stats.total_files = total.get("nFiles", 0)
        for lang, lang_data in data.items():
            if lang in ("SUM", "header"):
                continue
            stats.by_language[lang] = {
                "files": lang_data.get("nFiles", 0),
                "lines": lang_data.get("code", 0) + lang_data.get("blank", 0) + lang_data.get("comment", 0),
            }
        return stats
    except (OSError, json.JSONDecodeError, subprocess.TimeoutExpired):
        return None


def count_lines(workspace_path: str) -> CodeStats:
    """Count code lines in a project directory.

    Uses cloc as fast path when available, falls back to pure-Python scanner.

    Args:
        workspace_path: Absolute path to the project root.

    Returns:
        CodeStats with detailed line counts by language and file.
    """
    cloc_result = _try_cloc(workspace_path)
    if cloc_result:
        return cloc_result

    stats = CodeStats()
    by_language = defaultdict(lambda: {"files": 0, "lines": 0, "blank": 0, "comments": 0})
    file_sizes = []

    for root, dirs, files in os.walk(workspace_path):
        dirs[:] = [
            d for d in dirs
            if d not in SKIP_DIRS and not d.startswith(".")
        ]

        for filename in files:
            if filename in SKIP_FILES:
                continue
            if filename.startswith("."):
                continue

            ext = os.path.splitext(filename)[1].lower()
            if ext not in LANGUAGE_EXTENSIONS:
                if filename.lower() in ("dockerfile", "makefile", "cmakelists.txt"):
                    ext = f".{filename}".lower()
                else:
                    continue

            filepath = os.path.join(root, filename)
            counts = _count_file_lines(filepath, ext)
            if counts["lines"] == 0:
                continue

            stats.total_lines += counts["lines"]
            stats.total_blank_lines += counts["blank"]
            stats.total_comment_lines += counts["comments"]
            stats.total_files += 1

            lang = LANGUAGE_EXTENSIONS.get(ext, ext)
            by_language[lang]["files"] += 1
            by_language[lang]["lines"] += counts["lines"]
            by_language[lang]["blank"] += counts["blank"]
            by_language[lang]["comments"] += counts["comments"]

            rel_path = os.path.relpath(filepath, workspace_path)
            file_sizes.append({
                "path": rel_path,
                "lines": counts["lines"],
                "language": lang,
            })

    stats.by_language = dict(by_language)
    stats.largest_files = sorted(file_sizes, key=lambda x: x["lines"], reverse=True)[:15]

    return stats