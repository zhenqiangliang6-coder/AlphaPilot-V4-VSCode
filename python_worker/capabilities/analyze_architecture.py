# -*- coding: utf-8 -*-
"""Read-only architecture analyzer for AlphaPilot OS.

Responsibility:
  - 只读分析项目源码结构，提取 import 依赖、类/函数定义、模块职责。
  - 生成架构分析结果（模块依赖图、分层关系、数据流推断）。
  - 不创建/修改任何文件，不执行项目代码。

Output:
  - ArchitectureReport: 包含模块列表、依赖关系、架构层次、风险提示。
"""

from __future__ import annotations

import ast
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

DEFAULT_SKIP_DIRS: Set[str] = {
    ".git", ".svn", ".hg", ".venv", ".venv_worker", "venv",
    "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".tox", ".eggs", "dist", "build", "site-packages", "egg-info",
    ".idea", ".vscode", ".vs",
}

SKIP_FILE_PATTERNS: List[str] = [
    "test_*", "*_test.py", "conftest.py", "setup.py",
    "__pycache__", "*.pyc",
]


def _should_skip_dir(dirname: str) -> bool:
    return dirname in DEFAULT_SKIP_DIRS or dirname.startswith(".")


def _should_skip_file(filename: str) -> bool:
    from fnmatch import fnmatch
    return any(fnmatch(filename, pat) for pat in SKIP_FILE_PATTERNS)


@dataclass(frozen=True)
class ModuleInfo:
    """单个模块/文件的架构信息。"""
    path: str
    name: str
    imports: FrozenSet[str] = frozenset()
    classes: FrozenSet[str] = frozenset()
    functions: FrozenSet[str] = frozenset()
    docstring: str = ""
    lines: int = 0
    layer: str = "unknown"


@dataclass(frozen=True)
class ArchitectureReport:
    """完整的架构分析报告。"""
    root_path: str
    file_count: int
    module_count: int
    modules: Tuple[ModuleInfo, ...]
    dependencies: Tuple[Tuple[str, str], ...]
    layers: Dict[str, List[str]]
    risks: Tuple[str, ...] = ()
    mermaid_diagram: str = ""
    ascii_diagram: str = ""


def analyze_workspace_architecture(
    root_path: str,
    max_files: int = 200,
) -> ArchitectureReport:
    """只读分析工作区的架构。

    Args:
        root_path: 项目根目录绝对路径。
        max_files: 最大分析文件数，防止超大项目。

    Returns:
        ArchitectureReport: 结构化的架构分析结果。
    """
    root = Path(root_path).resolve()
    if not root.exists():
        return ArchitectureReport(
            root_path=root_path,
            file_count=0,
            module_count=0,
            modules=(),
            dependencies=(),
            layers={},
            risks=(f"路径不存在: {root_path}",),
        )

    modules: List[ModuleInfo] = []
    file_count = 0

    # 第一遍：收集所有模块的 import 信息
    module_imports: Dict[str, Set[str]] = {}  # module_name -> set of imported modules
    module_classes: Dict[str, Set[str]] = {}
    module_functions: Dict[str, Set[str]] = {}
    module_docstrings: Dict[str, str] = {}

    for py_file in root.rglob("*.py"):
        if file_count >= max_files:
            break

        rel_path = str(py_file.relative_to(root))

        # 跳过不应分析的路径
        parts = Path(rel_path).parts
        if any(_should_skip_dir(p) for p in parts):
            continue
        if _should_skip_file(py_file.name):
            continue

        try:
            with open(py_file, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
        except Exception:
            continue

        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        module_name = _module_name_from_path(rel_path)
        imports: Set[str] = set()
        classes: Set[str] = set()
        functions: Set[str] = set()
        docstring = ast.get_docstring(tree) or ""

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.ClassDef):
                classes.add(node.name)
            elif isinstance(node, ast.FunctionDef):
                if not node.name.startswith("_"):
                    functions.add(node.name)

        line_count = len(source.splitlines())

        module_imports[module_name] = imports
        module_classes[module_name] = classes
        module_functions[module_name] = functions
        module_docstrings[module_name] = docstring

        modules.append(ModuleInfo(
            path=rel_path,
            name=module_name,
            imports=frozenset(imports),
            classes=frozenset(classes),
            functions=frozenset(functions),
            docstring=docstring,
            lines=line_count,
            layer="unknown",
        ))

        file_count += 1

    # 第二遍：建立内部依赖关系
    internal_modules: Set[str] = set(module_imports.keys())
    dependencies: List[Tuple[str, str]] = []

    for mod_name, imports in module_imports.items():
        for imp in imports:
            if imp in internal_modules and imp != mod_name:
                dependencies.append((mod_name, imp))

    # 第三遍：分层推断
    layers = _infer_layers(modules, dependencies)

    # 第四遍：为每个模块标注层次
    annotated_modules = []
    for mod in modules:
        layer = "unknown"
        for layer_name, mod_names in layers.items():
            if mod.name in mod_names:
                layer = layer_name
                break
        annotated_modules.append(ModuleInfo(
            path=mod.path,
            name=mod.name,
            imports=mod.imports,
            classes=mod.classes,
            functions=mod.functions,
            docstring=mod.docstring,
            lines=mod.lines,
            layer=layer,
        ))

    # 第五遍：风险分析
    risks = _analyze_risks(annotated_modules, dependencies, root)

    # 第六遍：生成图表
    mermaid = _generate_mermaid(annotated_modules, dependencies, layers)
    ascii_diag = _generate_ascii(annotated_modules, layers)

    return ArchitectureReport(
        root_path=root_path,
        file_count=file_count,
        module_count=len(annotated_modules),
        modules=tuple(annotated_modules),
        dependencies=tuple(dependencies),
        layers=layers,
        risks=tuple(risks),
        mermaid_diagram=mermaid,
        ascii_diagram=ascii_diag,
    )


def _module_name_from_path(rel_path: str) -> str:
    """从相对路径提取模块名。"""
    parts = Path(rel_path).parts
    if parts[-1] == "__init__.py":
        return ".".join(parts[:-1]) if len(parts) > 1 else parts[0] if len(parts) == 1 else "root"
    name = parts[-1].replace(".py", "")
    if len(parts) > 1:
        return ".".join(list(parts[:-1]) + [name])
    return name


def _infer_layers(
    modules: List[ModuleInfo],
    dependencies: List[Tuple[str, str]],
) -> Dict[str, List[str]]:
    """基于模块名和依赖方向推断架构层次。"""
    layers: Dict[str, List[str]] = {
        "入口/启动层": [],
        "核心引擎层": [],
        "业务逻辑层": [],
        "数据/基础设施层": [],
        "工具/公共层": [],
        "外部接口层": [],
    }

    name_lower_to_module = {m.name.lower(): m.name for m in modules}

    for mod in modules:
        name_lower = mod.name.lower()
        parts = name_lower.split(".")

        # 按命名规则分类
        if any(kw in parts[-1] for kw in ["main", "app", "index", "start", "worker", "server"]):
            layers["入口/启动层"].append(mod.name)
        elif any(kw in name_lower for kw in ["core", "engine", "state_machine", "task_model", "protocol"]):
            layers["核心引擎层"].append(mod.name)
        elif any(kw in name_lower for kw in ["agent", "step_executor", "strategy", "skill", "persona"]):
            layers["业务逻辑层"].append(mod.name)
        elif any(kw in name_lower for kw in ["db", "database", "memory", "redis", "storage", "data", "cache"]):
            layers["数据/基础设施层"].append(mod.name)
        elif any(kw in name_lower for kw in ["util", "helper", "logger", "config", "tool"]):
            layers["工具/公共层"].append(mod.name)
        elif any(kw in name_lower for kw in ["api", "client", "http", "request", "router", "endpoint"]):
            layers["外部接口层"].append(mod.name)

    # 移除空层
    return {k: v for k, v in layers.items() if v}


def _analyze_risks(
    modules: List[ModuleInfo],
    dependencies: List[Tuple[str, str]],
    root: Path,
) -> List[str]:
    """分析架构风险。"""
    risks = []

    # 循环依赖检测
    dep_graph: Dict[str, Set[str]] = defaultdict(set)
    for src, dst in dependencies:
        dep_graph[src].add(dst)

    for src, dsts in dep_graph.items():
        for dst in dsts:
            if src in dep_graph.get(dst, set()):
                risks.append(f"循环依赖: {src} ↔ {dst}")

    # 跨层依赖检测
    for src, dst in dependencies:
        src_mod = next((m for m in modules if m.name == src), None)
        dst_mod = next((m for m in modules if m.name == dst), None)
        if src_mod and dst_mod:
            if src_mod.layer == "工具/公共层" and dst_mod.layer == "核心引擎层":
                risks.append(f"工具层反向依赖核心层: {src} → {dst}")

    # 超大文件检测
    for mod in modules:
        if mod.lines > 500:
            risks.append(f"过大模块 (>{mod.lines}行): {mod.path}")

    # 无文档模块
    undocumented = [m.name for m in modules if not m.docstring and m.lines > 20]
    if len(undocumented) > 5:
        risks.append(f"{len(undocumented)} 个模块缺少 docstring: {', '.join(undocumented[:5])}...")

    return risks


def _generate_mermaid(
    modules: List[ModuleInfo],
    dependencies: List[Tuple[str, str]],
    layers: Dict[str, List[str]],
) -> str:
    """生成 Mermaid 架构图。"""
    lines = ["graph TB"]
    lines.append("    %% 架构分层")

    # 定义子图
    for layer_name, mod_names in layers.items():
        safe_name = layer_name.replace("/", "_")
        lines.append(f"    subgraph {safe_name}[\"{layer_name}\"]")
        for mod_name in mod_names:
            safe_id = mod_name.replace(".", "_").replace("-", "_")
            lines.append(f"        {safe_id}[\"{mod_name}\"]")
        lines.append("    end")

    # 依赖边
    lines.append("")
    for src, dst in dependencies:
        src_id = src.replace(".", "_").replace("-", "_")
        dst_id = dst.replace(".", "_").replace("-", "_")
        lines.append(f"    {src_id} --> {dst_id}")

    return "\n".join(lines)


def _generate_ascii(
    modules: List[ModuleInfo],
    layers: Dict[str, List[str]],
) -> str:
    """生成 ASCII 架构图。"""
    lines = ["┌─ 项目架构总览 ─────────────────────────────────────┐"]

    for layer_name, mod_names in layers.items():
        lines.append(f"│")
        lines.append(f"│  [{layer_name}]")
        for mod_name in sorted(mod_names):
            mod = next((m for m in modules if m.name == mod_name), None)
            detail = ""
            if mod:
                parts = [f"{len(mod.classes)}类", f"{len(mod.functions)}函数", f"{mod.lines}行"]
                detail = f" ({', '.join(parts)})"
            lines.append(f"│    ├── {mod_name}{detail}")

    lines.append(f"│")
    lines.append(f"└──────────────────────────────────────────────────────")

    return "\n".join(lines)