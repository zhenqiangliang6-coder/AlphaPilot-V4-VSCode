"""AlphaPilot E2E standalone writer — writes final_file_ops to disk without Extension.

v3.6: Post-processing quality pipeline:
  1. Deduplicate FileOps by path (keep last occurrence)
  2. Strip all Markdown code fences from content
  3. Split content at cross-language FILE markers
  4. Validate Python syntax and report issues
  5. Report missing dependencies (e.g., react-scripts)
"""

import os
import re
import json
import ast
import shutil
from pathlib import Path


def _strip_fences(text: str) -> str:
    """Remove all Markdown code fence lines from content."""
    if not text:
        return text
    lines = text.splitlines()
    cleaned = [line for line in lines if not line.strip().startswith("```")]
    return "\n".join(cleaned).strip()


_CROSS_LANG_MARKER = re.compile(r"^\s*//\s*(?:FILE|TEST|DOC):.*$", re.MULTILINE)


def _split_cross_lang(content: str) -> str:
    """If content contains cross-language FILE markers, keep only the first segment."""
    if not content:
        return content
    match = _CROSS_LANG_MARKER.search(content)
    if match:
        return content[:match.start()].strip()
    return content


def clean_content(content: str) -> str:
    """Apply all content cleaning passes."""
    content = _strip_fences(content)
    content = _split_cross_lang(content)
    return content.strip()


def check_python_syntax(content: str, path: str) -> list[str]:
    """Validate Python syntax. Returns list of error messages."""
    errors = []
    try:
        ast.parse(content)
    except SyntaxError as e:
        errors.append(f"  [SYNTAX ERROR] {path}:{e.lineno}: {e.msg}")
    return errors


def check_missing_imports(content: str, path: str) -> list[str]:
    """Check for common missing imports in Python files."""
    warnings = []
    if not path.endswith(".py"):
        return warnings
    if "Request" in content and "from fastapi import" in content and "Request" not in content.split("from fastapi import", 1)[1].split("\n", 1)[0]:
        warnings.append(f"  [WARN] {path}: 使用了 'Request' 但未在 fastapi 导入中声明")
    return warnings


def check_frontend_deps(file_ops: list) -> str | None:
    """Check frontend package.json for missing react-scripts."""
    for op in file_ops:
        if op.get("path", "").endswith("package.json"):
            content = op.get("content", "")
            if "react-scripts" in content and "react-scripts" not in op.get("content", ""):
                pass
            try:
                pkg = json.loads(clean_content(content))
                scripts = pkg.get("scripts", {})
                deps = pkg.get("dependencies", {})
                dev_deps = pkg.get("devDependencies", {})
                all_deps = {**deps, **dev_deps}
                for script_name, script_cmd in scripts.items():
                    if "react-scripts" in script_cmd:
                        if "react-scripts" not in all_deps:
                            return ("[WARN] frontend/package.json: scripts 引用了 'react-scripts'"
                                    " 但未在 dependencies/devDependencies 中声明")
            except json.JSONDecodeError:
                pass
    return None


def write_disk(workspace: Path, final_file_ops: list, overwrite: bool = True):
    """Write FileOps to disk with deduplication and cleaning."""
    # Step 1: Deduplicate by path (keep last)
    seen = {}
    for op in final_file_ops:
        path = op.get("path", "")
        if path:
            seen[path] = op

    written = []
    syntax_errors = []
    missing_imports = []

    for path, op in seen.items():
        content = op.get("content", "")
        if not path or not isinstance(content, str):
            continue

        clean = clean_content(content)
        if not clean:
            print(f"  [SKIP] {path}: 清洗后内容为空")
            continue

        # Validate Python syntax
        if path.endswith(".py"):
            syntax_errors.extend(check_python_syntax(clean, path))
            missing_imports.extend(check_missing_imports(clean, path))

        target = workspace / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not overwrite:
            continue
        target.write_text(clean, encoding="utf-8")
        written.append(str(target.relative_to(workspace)))

    if syntax_errors:
        print(f"\n[SYNTAX ERRORS]")
        for e in syntax_errors:
            print(e)

    if missing_imports:
        for w in missing_imports:
            print(w)

    return written


def checkout(output_dir: str, target_workspace: str, dry_run: bool = False):
    source = Path(output_dir)
    context_file = next(source.glob("_context.json"), None)
    if not context_file:
        print(f"[E2E] _context.json 未找到: {source}")
        return

    ctx = json.loads(context_file.read_text(encoding="utf-8"))
    file_ops = ctx.get("final_file_ops", [])
    print(f"[E2E] 发现 {len(file_ops)} 个 FileOp")

    # Check for multi-file content contamination
    for op in file_ops:
        content = op.get("content", "")
        markers = _CROSS_LANG_MARKER.findall(content)
        if markers:
            print(f"  [FIX] {op['path']}: 包含跨语言标记 {markers}, 自动分离")

    # Check frontend deps
    deps_warn = check_frontend_deps(file_ops)
    if deps_warn:
        print(deps_warn)

    target = Path(target_workspace)
    if dry_run:
        seen = set()
        for op in file_ops:
            p = op.get("path", op.get("file_path", "?"))
            if p in seen:
                continue
            seen.add(p)
            clean = clean_content(op.get("content", ""))
            markers = _CROSS_LANG_MARKER.findall(op.get("content", ""))
            tag = " [CROSS-LANG]" if markers else ""
            print(f"  [{op.get('op', '?')}] {p} ({len(clean)} 字节){tag}")
    else:
        written = write_disk(target, file_ops)
        print(f"\n[E2E] 写入 {len(written)} 个文件:")
        for w in written:
            print(f"  + {w}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", help="AlphaPilot 输出目录")
    parser.add_argument("--target", default="./task_system_project", help="目标工作区路径")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    checkout(args.output_dir, args.target, dry_run=args.dry_run)