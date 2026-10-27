# -*- coding: utf-8 -*-
"""
E3 诊断脚本：架构意图的证据生产链与准入链契约审计

只读 · 不修改产品代码 · 仅调用已有函数并记录全部诊断字段

用法:
    cd python_worker
    .\.venv_worker\Scripts\python -m tests.diagnostic_e3_evidence_gap
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# 确保项目根在 sys.path（父目录以匹配 "python_worker" 包名）
_owd = os.getcwd()
_parent_dir = str(Path(_owd).parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
_project_root = Path(_owd)

# =========================================================
# 被测对象（只导入，不改代码）
# =========================================================
from python_worker.agents.qwen.qwen_worker_v2 import (
    _extract_evidence_keywords,
    build_execution_chain,
)
from python_worker.context_builder import search_project_files
from python_worker.collaboration_modes import prepare_collaboration_mode
from python_worker.task_state_contract import (
    EvidenceGate,
    validate_workspace_evidence,
)
from python_worker.capability_registry import get_registry

# =========================================================
# 测试工作区（固定，确保可复现）
# =========================================================
WORKSPACE_PATH = str(_project_root)
ARCHITECT_INTENT = "architecture"
ARCHITECT_MODE = "architect"
ARCHITECT_PERSONA = "architect"

# =========================================================
# E3 测试用例
# =========================================================
E3_CASES = {
    "E3-A": "分析当前项目的整体架构",
    "E3-B": "分析 qwen_worker_v2.py 的架构职责",
    "E3-C": "分析模块依赖、调用关系和分层结构",
    "E3-D": "分析当前项目的整体架构",
}


def _safe_len(x):
    """安全取长度，失败返回 -1"""
    try:
        return len(x)
    except TypeError:
        return -1


def _safe_keys(x):
    """安全取 keys，失败返回空列表"""
    try:
        return list(x.keys())
    except (AttributeError, TypeError):
        return []


def simulate_capability_engine(workspace_path: str) -> Dict[str, Any]:
    """
    模拟 Phase C Capability Engine 对 architecture intent 的执行。
    architecture 的 profile: ws_dep="read_only", scan=True
    → 应触发 structure.tree, structure.mermaid, workspace.scan, arch.analyze
    """
    result = {}
    try:
        registry = get_registry()
        # 只解析 architecture 相关的只读扫描能力
        resolved = registry.resolve_all(
            [
                "structure.tree",
                "structure.mermaid",
                "workspace.scan",
                "arch.analyze",
            ]
        )
        context: Dict[str, Any] = {}
        capability_results: Dict[str, Any] = {}
        resolve_and_execute_capabilities_for(
            resolved, registry, workspace_path, context, capability_results
        )
        result = dict(capability_results)
    except Exception as exc:
        result["_error"] = str(exc)
    return result


def resolve_and_execute_capabilities_for(
    resolved, registry, workspace_path, context, capability_results
):
    """内联版 capability 执行，使用真实模块路径（scan_workspace + render_structure + analyze_architecture）。"""
    tree_result = None

    if "structure.tree" in resolved.resolved_ids or "workspace.scan" in resolved.resolved_ids:
        from python_worker.capabilities.scan_workspace import scan_workspace, TreeResult

        tree_result = scan_workspace(workspace_path)

    if "structure.tree" in resolved.resolved_ids and tree_result:
        from python_worker.capabilities.render_structure import tree_to_text

        capability_results["structure.tree"] = tree_to_text(tree_result)

    if "structure.mermaid" in resolved.resolved_ids and tree_result:
        from python_worker.capabilities.render_structure import tree_to_mermaid

        capability_results["structure.mermaid"] = tree_to_mermaid(tree_result)

    if "workspace.scan" in resolved.resolved_ids and tree_result:
        capability_results["workspace.scan"] = {
            "file_count": tree_result.file_count,
            "directory_count": tree_result.directory_count,
            "truncated": tree_result.truncated,
        }

    if "arch.analyze" in resolved.resolved_ids:
        from python_worker.capabilities.analyze_architecture import analyze_workspace_architecture

        arch = analyze_workspace_architecture(workspace_path)
        capability_results["arch.analyze"] = {
            "file_count": arch.file_count,
            "module_count": arch.module_count,
            "dependencies": list(arch.dependencies),
            "layers": dict(arch.layers),
            "risks": list(arch.risks),
            "mermaid_diagram": arch.mermaid_diagram,
            "ascii_diagram": arch.ascii_diagram,
        }


def run_e3_case(
    case_id: str,
    prompt: str,
    workspace_path: str,
    *,
    skip_capability_engine: bool = False,
) -> Dict[str, Any]:
    """
    模拟 architecture intent 从 Phase C 到 Phase D 到 EvidenceGate 的完整流程。
    """
    log: Dict[str, Any] = {
        "case_id": case_id,
        "prompt": prompt,
        "workspace_path": workspace_path,
        "timestamp": datetime.now().isoformat(),
        "intent": ARCHITECT_INTENT,
    }

    # ── Phase C: Capability Engine ──
    capability_results: Dict[str, Any] = {}
    if not skip_capability_engine:
        capability_results = simulate_capability_engine(workspace_path)
    log["capability_engine"] = {
        "available": bool(capability_results) and "_error" not in capability_results,
        "keys": [k for k in capability_results if k != "_error"],
        "arch_analyze_module_count": capability_results.get("arch.analyze", {}).get(
            "module_count", 0
        ),
        "error": capability_results.get("_error", None),
    }

    # ── Execution Chain ──
    raw_chain = build_execution_chain(ARCHITECT_INTENT, prompt)
    _mode, _prompt, final_chain = prepare_collaboration_mode(
        ARCHITECT_MODE, prompt, raw_chain, preserve_chain=False, intent=ARCHITECT_INTENT
    )
    log["execution_chain"] = {
        "raw": list(raw_chain),
        "after_g4_2": list(final_chain),
        "workspace_in_chain": "workspace" in final_chain,
    }

    # ── Phase D: Evidence Collection ──
    ws_path = workspace_path
    project_context_files: List[str] = []
    source_files: Dict[str, str] = {}
    workspace_scan = None  # architecture intent 不在此分支

    _ws_path = ws_path
    strategy = "none"
    search_keywords: List[str] = []
    matched_files_before: List[str] = []

    workspace_evidence: Dict[str, str] = {}
    evidence_search_hits: List[Dict] = []
    search_result: Dict[str, Any] = {"files": {}, "hits": [], "errors": []}

    if "workspace" in final_chain and _ws_path and os.path.isdir(_ws_path):
        # Phase D 主路径：扫描 → 映射
        strategy = "direct_mapping" if (project_context_files or source_files) else "fallback_keyword_search"
        for fpath in project_context_files:
            full_path = os.path.join(_ws_path, fpath)
            if os.path.isfile(full_path):
                workspace_evidence[fpath] = f"[content_of_{fpath}]"
                evidence_search_hits.append(
                    {"path": fpath, "line": 1, "match": "project_context"}
                )
        for fpath, content in source_files.items():
            workspace_evidence[fpath] = content
            evidence_search_hits.append(
                {"path": fpath, "line": 1, "match": "source_file"}
            )
        # Fallback 关键词搜索
        if not workspace_evidence:
            strategy = "fallback_keyword_search"
            search_keywords = _extract_evidence_keywords(prompt)
            matched_before = set(workspace_evidence.keys())
            search_result = search_project_files(_ws_path, search_keywords)
            workspace_evidence = search_result.get("files", {})
            evidence_search_hits = search_result.get("hits", [])
            matched_files_before = list(matched_before)
    else:
        strategy = "skipped"

    log["evidence_collection"] = {
        "strategy": strategy,
        "project_context_files_count": _safe_len(project_context_files),
        "source_files_count": _safe_len(source_files),
        "search_keywords": search_keywords,
        "matched_files_count": _safe_len(workspace_evidence),
        "matched_files": _safe_keys(workspace_evidence)[:15],
        "search_hits_count": _safe_len(evidence_search_hits),
        "search_errors": search_result.get("errors", [])
        if strategy == "fallback_keyword_search"
        else [],
    }

    # ── EvidenceGate ──
    meta: Dict[str, Any] = {
        "workspace_evidence": workspace_evidence,
        "evidence_search_hits": evidence_search_hits,
        "workspace_path": _ws_path,
    }
    gate: EvidenceGate = validate_workspace_evidence(meta)

    log["evidence_gate"] = {
        "result": "passed" if gate.can_proceed() else "failed",
        "status": str(gate.status),
        "failure_reason": gate.failure_reason,
        "acquired_items": len(gate.files_read),
        "required": gate.required,
    }

    log["final_task_status"] = "would_pass" if gate.can_proceed() else "would_fail"

    return log


# =========================================================
# 主入口
# =========================================================
def main():
    print("=" * 72)
    print("  E3 诊断：architecture intent 证据生产链与准入链契约审计")
    print(f"  工作区: {WORKSPACE_PATH}")
    print(f"  时间:   {datetime.now().isoformat()}")
    print("=" * 72)

    results: List[Dict[str, Any]] = []

    for case_id, prompt in E3_CASES.items():
        print(f"\n{'─' * 72}")
        print(f"  [{case_id}] {prompt}")
        print(f"{'─' * 72}")

        skip_cap = (case_id == "E3-D")
        if skip_cap:
            print("  ⚠ E3-D 跳过 Capability Engine（模拟无 scan 对比）")

        log = run_e3_case(
            case_id, prompt, WORKSPACE_PATH, skip_capability_engine=skip_cap
        )
        results.append(log)

        # 即时输出关键结论
        ec = log["evidence_collection"]
        eg = log["evidence_gate"]
        ce = log["capability_engine"]
        ex = log["execution_chain"]

        print(f"  Chain:          {ex['after_g4_2']}")
        print(f"  Capability:     {ce['available']} (keys: {ce['keys']}, modules: {ce['arch_analyze_module_count']})")
        print(f"  Strategy:       {ec['strategy']}")
        print(f"  Keywords:       {ec['search_keywords']}")
        print(f"  Matched files:  {ec['matched_files_count']}")
        if ec['matched_files']:
            for f in ec['matched_files'][:8]:
                print(f"    - {f}")
        print(f"  EvidenceGate:   {eg['result']}")
        if eg['failure_reason']:
            print(f"  Failure reason: {eg['failure_reason']}")
        print(f"  Would task:     {log['final_task_status']}")

    # ── 汇总 ──
    print(f"\n{'=' * 72}")
    print("  汇总")
    print(f"{'=' * 72}")
    print(f"  {'Case':<8} {'Strategy':<28} {'Keywords':<30} {'Files':>6} {'Gate':>8} {'Outcome':>10}")
    print(f"  {'─'*8} {'─'*28} {'─'*30} {'─'*6} {'─'*8} {'─'*10}")
    for r in results:
        ec = r["evidence_collection"]
        eg = r["evidence_gate"]
        kw = ", ".join(ec["search_keywords"][:4]) if ec["search_keywords"] else "(none)"
        kw = kw[:28] + ".." if len(kw) > 28 else kw
        print(
            f"  {r['case_id']:<8} {ec['strategy']:<28} {kw:<30} "
            f"{ec['matched_files_count']:>6} {eg['result']:>8} {r['final_task_status']:>10}"
        )

    # ── 写入 JSON 供后续分析 ──
    output_path = _project_root / "tests" / "e3_diagnostic_output.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n完整 JSON 输出: {output_path}")

    # ── 结论提示 ──
    all_passed = all(r["evidence_gate"]["result"] == "passed" for r in results)
    any_skipped = any(
        r["evidence_collection"]["strategy"] == "skipped" for r in results
    )
    all_fallback = all(
        r["evidence_collection"]["strategy"] == "fallback_keyword_search"
        for r in results
    )

    print(f"\n{'=' * 72}")
    print("  结论")
    print(f"{'=' * 72}")
    if all_passed:
        print("  ✅ 所有 E3 用例 EvidenceGate 放行。")
        print("     但注意：放行 ≠ 证据与 architecture intent 真正匹配。")
    elif any_skipped:
        print("  ❌ 存在 Phase D 跳过的用例：workspace 未进入执行链。")
    elif all_fallback:
        print("  ⚠️  所有用例依赖 fallback 关键词搜索。")
        print("     这意味着 Phase D 没有复用 Capability Engine 的扫描结果。")
    print("  📌 E3 是证据生产链与准入链之间的契约问题，不只是关键词命中率。")


if __name__ == "__main__":
    main()