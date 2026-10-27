# -*- coding: utf-8 -*-
"""Deterministic renderers for workspace scan results.

Responsibility:
  - 将 TreeResult 转换为输出格式（文本树、Mermaid）。
  - 纯数据转换层，不再访问文件系统。
  - 输出内容 100% 由输入决定，无随机性、无 LLM 参与。

Boundary:
  - 此模块不验证 TreeResult 的真实性——调用方负责先通过 scan_workspace 获取真实数据。
  - Mermaid 使用 flowchart TD（而非 mindmap），方便后续节点定位与交互。
"""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import List

from .scan_workspace import TreeNode, TreeResult


def tree_to_text(result: TreeResult) -> str:
    """生成人类可读的 ASCII 目录树。

    Returns:
        str: 包含根名称、树形结构和统计信息的文本块。
    """
    lines: List[str] = [result.root.name]

    def visit(node: TreeNode, prefix: str) -> None:
        visible = node.children if node.children else ()
        for index, child in enumerate(visible):
            last = index == len(visible) - 1
            connector = "└── " if last else "├── "
            suffix = "/" if child.kind == "directory" else ""
            lines.append(f"{prefix}{connector}{child.name}{suffix}")
            if child.kind == "directory":
                next_prefix = prefix + ("    " if last else "│   ")
                visit(child, next_prefix)

    visit(result.root, "")

    summary_parts = [f"{result.file_count} files", f"{result.directory_count} directories"]
    if result.truncated:
        summary_parts.append("truncated")
    if result.skipped_symlinks > 0:
        summary_parts.append(f"{result.skipped_symlinks} symlinks skipped")

    lines.append("")
    lines.append(f"  [{', '.join(summary_parts)}]")

    if result.walk_errors:
        lines.append(f"  [{len(result.walk_errors)} path errors during scan]")

    return "\n".join(lines)


def tree_to_mermaid(result: TreeResult) -> str:
    """从 TreeResult 生成确定性的 Mermaid flowchart TD。

    设计原则：
      - 使用 flowchart TD（自上而下），节点 ID 基于相对路径的确定性哈希。
      - 目录节点用圆角矩形，文件节点用标准矩形。
      - 保持层级缩进以方便阅读 Mermaid 源码。

    Returns:
        str: Mermaid flowchart 源码块（不含外层 ```mermaid 包围）。
    """
    lines: List[str] = ["flowchart TD"]

    def node_id(rel_path: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9_]", "_", rel_path)
        safe = re.sub(r"_+", "_", safe).strip("_")
        if not safe:
            safe = "root"
        if safe[0].isdigit():
            safe = f"n_{safe}"
        return safe

    def emit_node(node: TreeNode, indent: str = "  ") -> None:
        nid = node_id(node.relative_path)
        if node.kind == "directory":
            line = f'{indent}{nid}[{_escape_mermaid_label(node.name)}/]'
        else:
            line = f'{indent}{nid}[{_escape_mermaid_label(node.name)}]'
        lines.append(line)

        for child in node.children:
            emit_node(child, indent + "  ")
            cid = node_id(child.relative_path)
            lines.append(f"{indent}  {nid} --> {cid}")

    emit_node(result.root)

    lines.append("")
    lines.append(f'  %% {result.file_count} files, {result.directory_count} dirs')
    if result.truncated:
        lines.append(f"  %% truncated at max nodes or depth")
    if result.skipped_symlinks > 0:
        lines.append(f"  %% {result.skipped_symlinks} symlinks skipped")
    if result.walk_errors:
        for err in result.walk_errors[:5]:
            lines.append(f"  %% walk error: {err}")

    return "\n".join(lines)


def _escape_mermaid_label(name: str) -> str:
    """转义方括号以确保 Mermaid 正确解析节点标签。"""
    return name.replace("[", "#91;").replace("]", "#93;").replace('"', "#quot;")