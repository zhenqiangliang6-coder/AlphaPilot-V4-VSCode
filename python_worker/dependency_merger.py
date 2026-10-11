# -*- coding: utf-8 -*-
"""
AlphaPilot 依赖合并器
-----------------------
将三种依赖信号源（manifest / AST import / DEPENDS marker）
合并去重，输出统一、可解释的依赖视图。

三种信号：
  ① Manifest   — 项目清单声明（requirements.txt, pyproject.toml, setup.py）
  ② AST import — 源码导入扫描（_imports_from_source → _infer_dependencies）
  ③ DEPENDS    — 协议标记（write_step 生成的 # DEPENDS: 指令）

输出：统一的 DependencyEntry 列表，标明每个依赖来自哪些信号源。
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DependencyEntry:
    """统一的依赖项记录"""

    name: str
    sources: list[str] = field(default_factory=list)
    version: Optional[str] = None
    manifest_files: list[str] = field(default_factory=list)
    import_modules: list[str] = field(default_factory=list)

    @property
    def in_manifest(self) -> bool:
        return "manifest" in self.sources

    @property
    def in_imports(self) -> bool:
        return "ast_import" in self.sources

    @property
    def in_depends(self) -> bool:
        return "depends" in self.sources

    @property
    def signal_count(self) -> int:
        return len(self.sources)


# ---- 内部工具 -----------------------------------------------------------------

def _normalize(name: str) -> str:
    """标准化包名：小写 + 去空格 + 去版本号后缀。"""
    return name.strip().lower().split("[")[0].split("=")[0].split(">")[0].split("<")[0].split("~")[0].split("!")[0].strip()


def _parse_version(name: str) -> tuple[str, Optional[str]]:
    """从带版本号的依赖名中分离包名和版本约束。"""
    cleaned = name.strip()
    for sep in ("==", ">=", "<=", "~=", ">", "<", "!="):
        if sep in cleaned:
            pkg, ver = cleaned.split(sep, 1)
            return _normalize(pkg), (sep + ver.strip())
    return _normalize(cleaned), None


# ---- 合并逻辑 -----------------------------------------------------------------

def merge_dependencies(
    manifest_deps: Optional[dict] = None,
    inferred_deps: Optional[list] = None,
    depends_deps: Optional[list] = None,
) -> list[DependencyEntry]:
    """
    合并三种信号源的依赖，去重并标注来源。

    参数:
        manifest_deps: {包名: 版本约束}，来自 manifest 文件解析
        inferred_deps: [包名, ...]，来自 AST 导入扫描
        depends_deps:  [包名, ...]，来自 DEPENDS 协议标记

    返回:
        list[DependencyEntry]: 统一去重后的依赖列表，按 name 排序
    """
    merged: dict[str, DependencyEntry] = {}

    manifest_deps = manifest_deps or {}
    inferred_deps = inferred_deps or []
    depends_deps = depends_deps or []

    # ① Manifest 信号
    for raw_name, version in manifest_deps.items():
        name = _normalize(raw_name)
        if not name:
            continue
        if name not in merged:
            merged[name] = DependencyEntry(name=name)
        entry = merged[name]
        if "manifest" not in entry.sources:
            entry.sources.append("manifest")
        if version:
            entry.version = version
        manifest_file = version if isinstance(version, str) and version.startswith("@") else None
        if manifest_file:
            entry.version = None
        # 保留原始 requirements 行用于追溯
        original = raw_name if raw_name != name else None

    # ② AST import 信号
    for dep in inferred_deps:
        name = _normalize(dep)
        if not name:
            continue
        if name not in merged:
            merged[name] = DependencyEntry(name=name)
        entry = merged[name]
        if "ast_import" not in entry.sources:
            entry.sources.append("ast_import")
        if dep not in entry.import_modules:
            entry.import_modules.append(dep)

    # ③ DEPENDS 信号
    for dep in depends_deps:
        name = _normalize(dep)
        if not name:
            continue
        if name not in merged:
            merged[name] = DependencyEntry(name=name)
        entry = merged[name]
        if "depends" not in entry.sources:
            entry.sources.append("depends")

    result = sorted(merged.values(), key=lambda e: e.name)
    return result


def dependency_summary(entries: list[DependencyEntry]) -> dict:
    """生成合并依赖的统计摘要。"""
    return {
        "total": len(entries),
        "by_source": {
            "manifest": sum(1 for e in entries if e.in_manifest),
            "ast_import": sum(1 for e in entries if e.in_imports),
            "depends": sum(1 for e in entries if e.in_depends),
        },
        "multi_signal": sum(1 for e in entries if e.signal_count >= 2),
        "manifest_only": sum(1 for e in entries if e.sources == ["manifest"]),
        "import_only": sum(1 for e in entries if e.sources == ["ast_import"]),
        "depends_only": sum(1 for e in entries if e.sources == ["depends"]),
        "all_three": sum(1 for e in entries if e.signal_count == 3),
    }


def format_dependency_report(entries: list[DependencyEntry]) -> str:
    """生成人类可读的依赖报告字符串。"""
    if not entries:
        return "No dependencies detected."

    lines = [f"Unified dependencies ({len(entries)} total):", "-" * 50]
    for e in entries:
        sources_str = "+".join(e.sources)
        version_str = f" {e.version}" if e.version else ""
        lines.append(f"  {e.name}{version_str}  [{sources_str}]")
    lines.append("-" * 50)

    summary = dependency_summary(entries)
    lines.append(f"Manifest: {summary['by_source']['manifest']}  "
                  f"AST: {summary['by_source']['ast_import']}  "
                  f"DEPENDS: {summary['by_source']['depends']}  "
                  f"Multi-signal: {summary['multi_signal']}")
    return "\n".join(lines)