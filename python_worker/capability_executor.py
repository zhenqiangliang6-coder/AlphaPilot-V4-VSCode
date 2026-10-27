# -*- coding: utf-8 -*-
"""G1.2：能力执行器 — Skill.capabilities → Native Tool 的桥接层。

职责：
  - 接收 matched_skill + context + payload
  - resolve_all → execute → validate_result → 注入 context
  - 不修改执行链、不跳过 LLM、不改变任务状态

设计约束：
  - resolve 和 execute 是两个独立操作
  - 能力未注册 → 记录警告，降级 LLM（不阻断任务）
  - 执行失败 → 记录错误，降级 LLM（不阻断任务）
  - 只读工具的结果注入 context，不写文件
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from .capability_registry import (
        CapabilityNotAvailable,
        CapabilityRegistry,
        ResolvedCapabilities,
        get_registry,
    )
    from .capabilities.scan_workspace import TreeResult
except ImportError:
    from capability_registry import (
        CapabilityNotAvailable,
        CapabilityRegistry,
        ResolvedCapabilities,
        get_registry,
    )
    from capabilities.scan_workspace import TreeResult


def resolve_and_execute_capabilities(
    selected_skill: Any,
    context: dict,
    payload: dict,
    registry: Optional[CapabilityRegistry] = None,
) -> None:
    """解析 Skill 声明的能力，执行已注册的原生工具，结果注入 context。

    Args:
        selected_skill: route_skill() 返回的 Skill 数据类实例。
        context: Worker 任务上下文（会被原位修改）。
        payload: 任务 payload，从中提取 workspace_path。
        registry: 可选的能力注册中心（默认使用全局单例）。
    """
    capabilities = getattr(selected_skill, "capabilities", None)
    if not capabilities:
        return

    _log(f"Skill '{selected_skill.id}' 声明能力: {capabilities}")

    if registry is None:
        registry = get_registry()

    try:
        resolved = registry.resolve_all(capabilities)
    except CapabilityNotAvailable as e:
        _log(f"能力未注册: {e.missing}，降级至 LLM 路径")
        return

    workspace_path = _extract_workspace_path(payload)
    capability_results = context.setdefault("_capability_results", {})

    if resolved.has("workspace.scan"):
        if not workspace_path or not str(workspace_path).strip():
            capability_results["workspace.scan"] = {
                "status": "blocked",
                "error": "工作区路径缺失：payload 未提供 workspace_path 或 project_path",
            }
            _log("workspace.scan 被阻断: 路径缺失")
        else:
            _execute_workspace_scan(
                resolved, registry, workspace_path, context, capability_results
            )

    tree_result = context.get("_tree_result")

    if tree_result is not None:
        if resolved.has("structure.tree"):
            _execute_structure_tree(resolved, registry, tree_result, capability_results)

        if resolved.has("structure.mermaid"):
            _execute_structure_mermaid(resolved, registry, tree_result, capability_results)

    if resolved.has("arch.analyze"):
        if workspace_path and str(workspace_path).strip():
            _execute_arch_analyze(resolved, registry, workspace_path, context, capability_results)
        else:
            capability_results["arch.analyze"] = {
                "status": "blocked",
                "error": "arch.analyze 需要有效的工作区路径",
            }
            _log("arch.analyze 被阻断: 路径缺失")

    _log(f"执行完成: {len(capability_results)} 个能力结果已注入 context")


def _execute_workspace_scan(
    resolved: ResolvedCapabilities,
    registry: CapabilityRegistry,
    workspace_path: str,
    context: dict,
    capability_results: dict,
) -> None:
    scan_result = registry.execute(
        resolved, "workspace.scan",
        root_path=workspace_path, max_depth=4, max_nodes=500,
    )
    if not scan_result.success:
        _log(f"workspace.scan 执行失败: {scan_result.error}")
        capability_results["workspace.scan"] = {
            "status": "failed",
            "error": str(scan_result.error) if scan_result.error else "扫描执行失败",
        }
        return

    validated = registry.validate_result(
        "workspace.scan", scan_result,
        expected_root_path=str(Path(workspace_path).resolve()),
    )
    if not validated.success:
        _log(f"workspace.scan 验证失败: {validated.error}")
        capability_results["workspace.scan"] = {
            "status": "validation_failed",
            "error": str(validated.error) if validated.error else "结果验证失败",
        }
        return

    tree_result = validated.data
    context["_tree_result"] = tree_result
    capability_results["workspace.scan"] = {
        "status": "succeeded",
        "file_count": tree_result.file_count,
        "directory_count": tree_result.directory_count,
        "truncated": tree_result.truncated,
        "scan_timestamp": tree_result.scan_timestamp,
        "as_dict": tree_result.as_dict() if hasattr(tree_result, "as_dict") else None,
    }
    _log(
        f"workspace.scan ✓: {tree_result.file_count} 文件, "
        f"{tree_result.directory_count} 目录"
        + (" (截断)" if tree_result.truncated else "")
    )


def _execute_structure_tree(
    resolved: ResolvedCapabilities,
    registry: CapabilityRegistry,
    tree_result: TreeResult,
    capability_results: dict,
) -> None:
    tree_output = registry.execute(resolved, "structure.tree", result=tree_result)
    if tree_output.success:
        capability_results["structure.tree"] = tree_output.data
        _log(f"structure.tree ✓ ({len(tree_output.data)} 字符)")
    else:
        _log(f"structure.tree 失败: {tree_output.error}")


def _execute_structure_mermaid(
    resolved: ResolvedCapabilities,
    registry: CapabilityRegistry,
    tree_result: TreeResult,
    capability_results: dict,
) -> None:
    mermaid_output = registry.execute(resolved, "structure.mermaid", result=tree_result)
    if mermaid_output.success:
        capability_results["structure.mermaid"] = mermaid_output.data
        _log(f"structure.mermaid ✓ ({len(mermaid_output.data)} 字符)")
    else:
        _log(f"structure.mermaid 失败: {mermaid_output.error}")


def _extract_workspace_path(payload: dict) -> Optional[str]:
    path = payload.get("workspace_path") or payload.get("project_path")
    if path is not None and str(path).strip():
        return str(path)
    return None


def _execute_arch_analyze(
    resolved: ResolvedCapabilities,
    registry: CapabilityRegistry,
    workspace_path: str,
    context: dict,
    capability_results: dict,
) -> None:
    arch_output = registry.execute(resolved, "arch.analyze", root_path=workspace_path)
    if not arch_output.success:
        _log(f"arch.analyze 执行失败: {arch_output.error}")
        return

    arch_report = arch_output.data
    capability_results["arch.analyze"] = {
        "file_count": arch_report.file_count,
        "module_count": arch_report.module_count,
        "dependencies": list(arch_report.dependencies),
        "layers": dict(arch_report.layers),
        "risks": list(arch_report.risks),
        "mermaid_diagram": arch_report.mermaid_diagram,
        "ascii_diagram": arch_report.ascii_diagram,
    }
    _log(
        f"arch.analyze ✓: {arch_report.module_count} 模块, "
        f"{len(arch_report.dependencies)} 依赖, "
        f"{len(arch_report.risks)} 风险"
    )


def _log(message: str) -> None:
    print(f"[Capability] {message}")