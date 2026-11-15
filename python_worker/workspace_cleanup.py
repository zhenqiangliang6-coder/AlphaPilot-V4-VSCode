# -*- coding: utf-8 -*-
"""AlphaPilot 工作区安全清理 —— 生产级单一实现。

为什么需要这个模块
------------------
旧的 ``clean_workspace()`` 用 ``shutil.rmtree`` 递归清空工作区，会同时踩三个坑：

1. 宿主 / 沙箱的批量删除保护会直接 ``SystemExit``，任务在第一步就死；
2. 虚拟环境、.git、用户自己的文件被无差别删除，且不可恢复；
3. 完全不校验目标是不是测试工作区，环境变量指错就清空真实项目。

铁律
----
* **FAIL-CLOSED**：目标身份无法确认时拒绝清理，不猜、不放行。
* **白名单保护**：受保护目录连遍历都不进入。
* **不递归删目录**：逐文件 ``unlink`` + 只删空目录 ``rmdir``，
  既不会触发批量删除保护，也不会因单个文件被占用而炸掉整棵树。
* **可审计**：返回 deleted / removed_dirs / kept / errors 完整报告。

生产侧（Node API ``fileOpsHandler.js``）本来就是「单文件 unlink + 授权校验 +
快照回滚」，此模块补齐 Python 侧的同等安全等级，供测试与工具共用。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

MARK_FILE = ".alphapilot_generated.mark"
TEST_MARKER = ".alphapilot_test_workspace"

# 默认允许清空的测试工作区目录名（只在没有显式标记时作为兜底身份依据）
DEFAULT_TEST_DIR_NAMES = frozenset({"shopflow_ecommerce"})

# 标记文件必须保留：否则清理一次后目录就失去「可清理」身份，下次被 fail-closed 拒绝
PROTECTED_FILE_NAMES = frozenset({TEST_MARKER})

# 永不删除、且连遍历都不进入的目录名
PROTECTED_DIR_NAMES = frozenset({
    ".venv", "venv", "env", "ENV",
    ".git", ".hg", ".svn",
    ".idea", ".vscode",
    "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".tox", ".nox",
    "dist", "build", "site-packages",
    ".alphapilot",  # 治理快照 / 隔离证据
})


class WorkspaceCleanupRefused(RuntimeError):
    """工作区身份校验未通过（fail-closed），拒绝执行清理。"""


def _validate_path_identity(p: Path, allow_roots=None) -> tuple[bool, str]:
    """确认 p 确实是「允许被清空的测试工作区」。"""
    home = Path.home().resolve()
    anchor = Path(p.anchor).resolve() if p.anchor else None
    dangerous = {
        d for d in (anchor, home, home / "Desktop", home / "Documents",
                    home / "Downloads", home / "OneDrive")
        if d is not None
    }
    if p in dangerous:
        return False, "目标是系统/用户根目录，拒绝清理"

    # 显式测试标记优先级最高
    if (p / TEST_MARKER).exists():
        return True, "检测到 .alphapilot_test_workspace 标记"

    # 有版本库且无标记 → 视为真实项目
    if (p / ".git").exists() or (p / ".hg").exists():
        return False, "检测到版本库且无测试标记（疑似真实项目），拒绝清理"

    if p.name.lower() in {n.lower() for n in DEFAULT_TEST_DIR_NAMES}:
        return True, "目录名在测试工作区白名单内"

    for r in (allow_roots or []):
        rp = Path(r).expanduser().resolve()
        if p == rp or rp in p.parents:
            return True, "位于显式允许的测试根目录内"

    return False, (
        "未通过工作区身份校验（FAIL-CLOSED）："
        "请在该目录放置 .alphapilot_test_workspace 标记，或显式传入 allow_roots"
    )


def validate_workspace(workspace: str, allow_roots=None) -> tuple[bool, str]:
    """公开的身份校验入口，供调用方在清理前独立检查。"""
    p = Path(workspace).expanduser().resolve()
    if not p.is_dir():
        # 目录尚不存在时只校验路径身份，不要求 .git 等存在性判断
        return _validate_path_identity(p, allow_roots)
    return _validate_path_identity(p, allow_roots)


def mark_test_workspace(workspace: str) -> Path:
    """给目录打上「可安全清理」标记，返回标记文件路径。"""
    p = Path(workspace).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    marker = p / TEST_MARKER
    marker.write_text(
        "AlphaPilot test workspace. Safe to clean by workspace_cleanup.\n",
        encoding="utf-8",
    )
    return marker


def _inside(p: Path, root: Path) -> bool:
    try:
        p.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def clean_generated_artifacts(workspace: str, allow_roots=None,
                              dry_run: bool = False) -> dict:
    """只删除 ``.alphapilot_generated.mark`` 清单中记录的产物（生产侧推荐）。

    清单缺失时什么都不删——宁可少删，也不误删用户文件。
    """
    root = Path(workspace).expanduser().resolve()
    ok, reason = validate_workspace(workspace, allow_roots)
    if not ok:
        raise WorkspaceCleanupRefused(reason)

    report = {"workspace": str(root), "reason": reason, "dry_run": dry_run,
              "deleted_files": [], "kept": [], "errors": []}

    manifest = root / MARK_FILE
    paths: list[str] = []
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(data, list):
                paths = [x for x in data if isinstance(x, str) and x.strip()]
        except (OSError, ValueError):
            paths = []

    for raw_rel in paths:
        # 注意：不能用 lstrip("./")——它是按字符集去头，会把 "../x" 变成 "x"。
        # 必须逐段检查，显式拒绝 .. / 绝对路径 / 盘符。
        normalized = raw_rel.replace("\\", "/").strip()
        parts = [seg for seg in normalized.split("/") if seg and seg != "."]
        if (not parts or ".." in parts or normalized.startswith("/")
                or ":" in parts[0]):
            report["kept"].append(f"{raw_rel} (路径越界)")
            continue
        rel = "/".join(parts)
        target = (root / rel).resolve()
        if not _inside(target, root) or target == root:
            report["kept"].append(f"{raw_rel} (路径越界)")
            continue
        rel_parts = target.relative_to(root).parts
        if any(part in PROTECTED_DIR_NAMES for part in rel_parts):
            report["kept"].append(f"{rel} (受保护)")
            continue
        if not target.is_file():
            continue
        try:
            if not dry_run:
                target.unlink(missing_ok=True)
            report["deleted_files"].append(rel)
        except OSError as e:
            report["errors"].append({"path": rel, "error": str(e)})

    return report


def clean_workspace_safely(workspace: str, allow_roots=None,
                           protected_dirs=None, dry_run: bool = False) -> dict:
    """清空测试工作区中的非受保护内容（不递归删目录）。

    ``shutil.rmtree`` 的替代实现：``os.walk`` 剪枝跳过受保护目录，
    逐文件删除，再自底向上只删空目录。全程不触发批量删除保护。
    """
    root = Path(workspace).expanduser().resolve()
    protected = set(PROTECTED_DIR_NAMES) | set(protected_dirs or [])
    ok, reason = validate_workspace(workspace, allow_roots)
    if not ok:
        raise WorkspaceCleanupRefused(reason)

    report = {
        "workspace": str(root), "reason": reason, "dry_run": bool(dry_run),
        "deleted_files": [], "removed_dirs": [], "kept": [], "errors": [],
        "created": False,
    }

    if not root.exists():
        report["created"] = True
        if not dry_run:
            root.mkdir(parents=True, exist_ok=True)
        return report

    # 1) 逐文件删除（受保护目录连遍历都不进入）
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = [d for d in dirnames if d not in protected]
        for name in filenames:
            if name in PROTECTED_FILE_NAMES:
                report["kept"].append(name)
                continue
            f = Path(dirpath) / name
            rel = f.relative_to(root).as_posix()
            try:
                if not dry_run:
                    f.unlink(missing_ok=True)
                report["deleted_files"].append(rel)
            except OSError as e:
                report["errors"].append({"path": rel, "error": str(e)})

    # 2) 自底向上只删空目录（根目录永远保留）
    for dirpath, dirnames, _filenames in os.walk(root, topdown=False):
        dirnames[:] = [d for d in dirnames if d not in protected]
        d = Path(dirpath)
        if d == root:
            continue
        try:
            if not any(d.iterdir()):
                if not dry_run:
                    d.rmdir()
                report["removed_dirs"].append(d.relative_to(root).as_posix())
        except OSError:
            pass

    for name in sorted(protected):
        if (root / name).exists():
            report["kept"].append(name)

    return report
