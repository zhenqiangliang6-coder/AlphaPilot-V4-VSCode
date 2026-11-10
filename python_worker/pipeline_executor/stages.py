# -*- coding: utf-8 -*-
# pipeline_executor._stages — 内置阶段定义
# ---------------------------------------------------------
# 每个阶段封装：步骤序列 + Gate（准入） + OnComplete（后处理）。
# 阶段实例作为 PipelineContract.stages 的元素被 PipelineExecutor 调度。
# ---------------------------------------------------------

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from .contract import (
    PipelineStage,
    PlanArtifact,
    CodeArtifact,
    TestArtifact,
    FixArtifact,
    ChangelogArtifact,
)


# ============================================================
# Gate 函数 — context → bool 准入条件
# ============================================================

def _gate_always_true(_context: dict) -> bool:
    """无条件准入。"""
    return True


def _gate_always_true_safe(_context: dict) -> bool:
    """无条件准入（None 安全）。"""
    return True


def _gate_has_workspace(context: dict) -> bool:
    """确认工作区路径可用。"""
    ws = context.get("meta", {}).get("workspace_path", "")
    return bool(ws)


def _gate_has_file_ops(context: dict) -> bool:
    """确认存在文件操作记录（前序阶段已生成代码）。"""
    ops = context.get("final_file_ops", [])
    return len(ops) > 0


def _gate_has_plan(context: dict) -> bool:
    """确认计划已生成。"""
    artifact = context.get("_artifacts", {}).get("plan")
    return artifact is not None and bool(getattr(artifact, "text", ""))


# ============================================================
# OnComplete 回调 — context → context 后处理
# ============================================================

def _on_complete_preparatory(context: dict) -> dict:
    """Preparatory 阶段完成：提取 PlanArtifact。"""
    for result in reversed(context.get("intermediate_results", [])):
        if result.get("type") in ("analyze", "plan"):
            context.setdefault("_artifacts", {})["plan"] = PlanArtifact(
                text=result.get("text", ""),
                estimated_complexity=result.get("complexity", "medium"),
            )
            break
    return context


def _on_complete_generative(context: dict) -> dict:
    """Generative 阶段完成：提取 CodeArtifact + TestArtifact。"""
    artifacts = context.setdefault("_artifacts", {})

    file_ops = context.get("final_file_ops", [])
    if file_ops:
        from .contract import _infer_language
        artifacts["code"] = CodeArtifact(
            file_ops=file_ops,
            language=_infer_language(file_ops),
        )

    for result in reversed(context.get("intermediate_results", [])):
        if result.get("type") == "test":
            from .contract import _parse_test_counts
            text = result.get("text", "")
            passed, failed = _parse_test_counts(text)
            artifacts["test"] = TestArtifact(
                passed=passed,
                failed=failed,
                total=passed + failed,
                output_text=text,
                exec_success=(failed == 0),
            )
            break

    return context


def _on_complete_post(context: dict) -> dict:
    """PostProcess 阶段完成：提取 ChangelogArtifact。"""
    for result in reversed(context.get("intermediate_results", [])):
        if result.get("type") == "changelog":
            context.setdefault("_artifacts", {})["changelog"] = ChangelogArtifact(
                updated=result.get("updated", False),
                entry=result.get("entry", ""),
                file=result.get("file", ""),
            )
            break
    return context


# ============================================================
# 预置阶段实例
# ============================================================

def PreparatoryStage() -> PipelineStage:
    """理解阶段：analyze → workspace → plan。

    Gate: 工作区可用
    失败: 阻塞（required=True），不允许继续
    """
    return PipelineStage(
        name="preparatory",
        steps=["analyze", "workspace", "plan"],
        gate=_gate_has_workspace,
        on_complete=_on_complete_preparatory,
        retry=0,
        timeout_s=120,
        required=True,
    )


def GenerativeStage() -> PipelineStage:
    """生成阶段：write → refine → test → fix。

    Gate: 无条件（计划已在上阶段验证）
    重试: 1 次（整个阶段失败后可重试一次）
    失败: 阻塞
    """
    return PipelineStage(
        name="generative",
        steps=["write", "refine", "test", "fix"],
        gate=_gate_always_true,
        on_complete=_on_complete_generative,
        retry=1,
        timeout_s=300,
        required=True,
    )


def PostProcessStage() -> PipelineStage:
    """后处理阶段：changelog → doc → docstring → respond。

    Gate: 有文件操作记录
    失败: 非阻塞（不因 changelog 失败而拒绝返回用户结果）
    """
    return PipelineStage(
        name="post",
        steps=["changelog", "doc", "docstring", "respond"],
        gate=_gate_has_file_ops,
        on_complete=_on_complete_post,
        retry=0,
        timeout_s=120,
        required=False,
    )


def OperateStage() -> PipelineStage:
    """操作执行阶段（单步： operate）。

    用于 execute_operation 意图或复合请求的 Phase 2。
    """
    return PipelineStage(
        name="operate",
        steps=["operate"],
        gate=_gate_always_true,
        on_complete=None,
        retry=0,
        timeout_s=300,
        required=True,
    )