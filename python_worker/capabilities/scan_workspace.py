# -*- coding: utf-8 -*-
"""Read-only workspace scanner for AlphaPilot OS.

Responsibility:
  - 只读扫描工作区目录，生成结构化 TreeResult。
  - 不执行项目代码、不创建文件、不跟踪符号链接。
  - 返回节点数受 max_nodes 和 max_depth 限制，truncated=True 表示不完整。

Boundary:
  - 此模块是纯数据采集层，不含业务策略、无 LLM 调用、无副作用。
  - 接入 Worker 时需额外校验工作区路径是否位于授权范围内。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Dict, List, Literal, Optional, Set

NodeKind = Literal["directory", "file"]

DEFAULT_SKIP_DIRS: Set[str] = {
    ".git",
    ".svn",
    ".hg",
    ".venv",
    ".venv_worker",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    ".eggs",
    "dist",
    "build",
    "site-packages",
    "egg-info",
    ".idea",
    ".vscode",
    ".vs",
}

DEFAULT_MAX_DEPTH: int = 4
DEFAULT_MAX_NODES: int = 500


@dataclass(frozen=True)
class TreeNode:
    """不可变树节点，表示一个目录或文件。"""

    name: str
    relative_path: str
    kind: NodeKind
    children: tuple[TreeNode, ...] = ()

    @property
    def is_directory(self) -> bool:
        return self.kind == "directory"

    @property
    def is_file(self) -> bool:
        return self.kind == "file"


@dataclass(frozen=True)
class TreeResult:
    """工作区扫描的结构化结果。

    Attributes:
        root_path: 扫描的根目录绝对路径。
        scan_timestamp: ISO 8601 格式的扫描时间戳（UTC）。
        root: 根节点（目录，包含所有子节点）。
        file_count: 发现的文件总数。
        directory_count: 发现的目录总数（含根目录）。
        truncated: True 表示节点数或深度超限，结果不完整。
        skipped_symlinks: 被跳过的符号链接数量。
        walk_errors: 扫描过程中遇到的路径错误（非致命）。
    """

    root_path: str
    scan_timestamp: str
    root: TreeNode
    file_count: int
    directory_count: int
    truncated: bool
    skipped_symlinks: int
    walk_errors: List[str] = field(default_factory=list)

    @property
    def total_nodes(self) -> int:
        return self.file_count + self.directory_count

    def as_dict(self) -> Dict:
        """递归转换为纯 dict，供序列化使用。"""

        def node_to_dict(node: TreeNode) -> Dict:
            result: Dict = {
                "name": node.name,
                "relative_path": node.relative_path,
                "kind": node.kind,
            }
            if node.children:
                result["children"] = [node_to_dict(c) for c in node.children]
            return result

        return {
            "root_path": self.root_path,
            "scan_timestamp": self.scan_timestamp,
            "root": node_to_dict(self.root),
            "file_count": self.file_count,
            "directory_count": self.directory_count,
            "truncated": self.truncated,
            "skipped_symlinks": self.skipped_symlinks,
            "walk_errors": list(self.walk_errors),
        }


class WorkspaceScanError(RuntimeError):
    """工作区扫描不安全或不可用时抛出。"""

    def __init__(self, message: str, path: Optional[str] = None):
        self.path = path
        super().__init__(message)


def scan_workspace(
    root_path: str,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_nodes: int = DEFAULT_MAX_NODES,
    skip_dirs: Optional[Set[str]] = None,
    skip_globs: Optional[List[str]] = None,
) -> TreeResult:
    """只读扫描工作区目录，返回结构化 TreeResult。

    Args:
        root_path: 工作区根目录的绝对路径。
        max_depth: 最大递归深度（根目录深度=0，其直接子项深度=1）。
        max_nodes: 最大节点数（目录 + 文件），超出则截断。
        skip_dirs: 额外要跳过的目录名集合（会与 DEFAULT_SKIP_DIRS 合并）。
        skip_globs: 要跳过的文件 glob 模式列表（如 ["*.pyc", "*.o"]）。

    Returns:
        TreeResult: 包含完整树结构、统计信息和截断标志。

    Raises:
        WorkspaceScanError: 路径不存在、不是目录或不可访问。
        ValueError: 参数不合法。
    """
    if not isinstance(root_path, str) or not root_path.strip():
        raise ValueError("root_path 不能为空")

    if max_depth < 0:
        raise ValueError(f"max_depth 必须 >= 0，收到 {max_depth}")
    if max_nodes < 1:
        raise ValueError(f"max_nodes 必须 >= 1，收到 {max_nodes}")

    resolved = _resolve_root(root_path)
    effective_skip_dirs = DEFAULT_SKIP_DIRS | (skip_dirs or set())
    effective_skip_globs: List[str] = list(skip_globs or [])

    walk_errors: List[str] = []
    node_counter: List[int] = [0]
    file_counter: List[int] = [0]
    dir_counter: List[int] = [0]
    symlink_counter: List[int] = [0]
    truncated: List[bool] = [False]

    def should_skip(name: str, parent: Path) -> bool:
        if name in effective_skip_dirs:
            return True
        if name.startswith(".") and name not in {".env", ".env.example"}:
            return True
        full = parent / name
        if full.is_symlink():
            symlink_counter[0] += 1
            return True
        return False

    def file_matches_skip(name: str) -> bool:
        for pattern in effective_skip_globs:
            if fnmatch(name, pattern):
                return True
        return False

    def walk_dir(current: Path, depth: int) -> TreeNode:
        if node_counter[0] >= max_nodes:
            truncated[0] = True
            return TreeNode(
                name=current.name or current.as_posix(),
                relative_path=_relative_path(current, resolved),
                kind="directory",
            )

        # 收集当前目录下的条目
        entries: List[os.DirEntry] = []
        try:
            with os.scandir(current) as scan:
                for entry in scan:
                    entries.append(entry)
        except (OSError, PermissionError) as error:
            walk_errors.append(f"{current}: {error}")
            truncated[0] = True
            return TreeNode(
                name=current.name or current.as_posix(),
                relative_path=_relative_path(current, resolved),
                kind="directory",
            )

        entries.sort(key=lambda e: (not e.is_dir(), e.name.lower()))
        node_counter[0] += 1
        dir_counter[0] += 1

        if depth >= max_depth:
            # 截断：不递归进入子目录，但列出直接文件
            file_children = []
            for entry in entries:
                if not entry.is_dir() and not file_matches_skip(entry.name):
                    file_children.append(
                        TreeNode(
                            name=entry.name,
                            relative_path=_relative_path(
                                Path(entry.path), resolved
                            ),
                            kind="file",
                        )
                    )
                    file_counter[0] += 1
            truncated[0] = True
            return TreeNode(
                name=current.name or current.as_posix(),
                relative_path=_relative_path(current, resolved),
                kind="directory",
                children=tuple(file_children),
            )

        children: List[TreeNode] = []
        for entry in entries:
            if node_counter[0] >= max_nodes:
                truncated[0] = True
                break

            if entry.is_dir():
                entry_name = entry.name
                if should_skip(entry_name, current):
                    continue
                child_node = walk_dir(Path(entry.path), depth + 1)
                children.append(child_node)
            else:
                if file_matches_skip(entry.name):
                    continue
                if should_skip(entry.name, current):
                    continue
                children.append(
                    TreeNode(
                        name=entry.name,
                        relative_path=_relative_path(
                            Path(entry.path), resolved
                        ),
                        kind="file",
                    )
                )
                file_counter[0] += 1
                node_counter[0] += 1

        return TreeNode(
            name=current.name or current.as_posix(),
            relative_path=_relative_path(current, resolved),
            kind="directory",
            children=tuple(children),
        )

    root_node = walk_dir(resolved, 0)
    timestamp = datetime.now(timezone.utc).isoformat()

    return TreeResult(
        root_path=str(resolved),
        scan_timestamp=timestamp,
        root=root_node,
        file_count=file_counter[0],
        directory_count=dir_counter[0],
        truncated=truncated[0],
        skipped_symlinks=symlink_counter[0],
        walk_errors=walk_errors,
    )


def _resolve_root(root_path: str) -> Path:
    """校验并解析工作区根路径。"""
    try:
        resolved = Path(root_path).resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise WorkspaceScanError(
            f"无法解析工作区路径: {root_path}", path=root_path
        ) from error

    if not resolved.exists():
        raise WorkspaceScanError(
            f"工作区路径不存在: {root_path}", path=root_path
        )
    if not resolved.is_dir():
        raise WorkspaceScanError(
            f"工作区路径不是目录: {root_path}", path=root_path
        )
    if not os.access(str(resolved), os.R_OK):
        raise WorkspaceScanError(
            f"工作区路径不可读: {root_path}", path=root_path
        )
    return resolved


def _relative_path(absolute: Path, root: Path) -> str:
    try:
        return absolute.relative_to(root).as_posix()
    except ValueError:
        return absolute.as_posix()