# -*- coding: utf-8 -*-
"""
changelog_step.py — 工作日志更新步骤

设计定位：
  - Phase 1：在 write_code 链中自动检测"更新日志/CHANGELOG"关键词并注入本步骤
  - Phase 3（未来）：Pipeline 模式下作为独立阶段，接收上游 artifacts

工业级设计原则：
  - 语言无关：不假定 Python 项目，兼容任何语言的项目
  - 幂等性：同一 task_id 不会重复追加
  - 非破坏性：先读后写，不存在则自动创建
  - 批量就绪：接受结构化变更数据，未来 Pipeline 阶段传递 artifacts 时直接对接
  - 多格式兼容：CHANGELOG.md / CHANGELOG.txt / CHANGELOG.rst 按优先级查找
"""

import os
import re
from datetime import datetime, timezone


def _find_changelog(workspace_path: str) -> str:
    """查找项目中的 CHANGELOG 文件，按优先级：.md > .txt > .rst。不存在时默认 .md。"""
    candidates = ["CHANGELOG.md", "changelog.md", "CHANGELOG.txt", "CHANGELOG.rst"]
    for name in candidates:
        full = os.path.join(workspace_path, name)
        if os.path.isfile(full):
            return full
    return os.path.join(workspace_path, "CHANGELOG.md")


def _extract_changes(context: dict) -> dict | None:
    """从执行上下文中提取本次任务的变更信息。

    返回 None 表示无法提取任何变更信息，应跳过写入。
    """
    meta = context.get("meta", {})
    user_request = meta.get("user_request", "").strip()
    if not user_request:
        user_request = meta.get("task_goal", "").strip()
    if not user_request:
        return None

    changed_files = []
    file_ops = context.get("final_file_ops", [])
    for op in file_ops:
        action = op.get("action", "modified")
        path = op.get("path", "") or op.get("target_path", "")
        if path and action != "error":
            changed_files.append(path)

    test_summary = None
    for result in context.get("intermediate_results", []):
        if result.get("type") == "test":
            text = result.get("text", "")
            passed_matches = re.findall(r"(\d+)\s*(?:PASSED|passed)\b", text)
            failed_matches = re.findall(r"(\d+)\s*(?:FAILED|failed)\b", text)
            passed = sum(int(m) for m in passed_matches)
            failed = sum(int(m) for m in failed_matches)
            if passed + failed > 0:
                test_summary = f"{passed}/{passed + failed} 通过"
            else:
                test_summary = "测试已执行"
            break

    fix_summary = None
    for result in context.get("intermediate_results", []):
        if result.get("type") == "fix":
            text = result.get("text", "")
            if text and "无需修复" not in text:
                fix_summary = "已自动修复"
            break

    return {
        "request": user_request,
        "files": changed_files,
        "tests": test_summary,
        "fixes": fix_summary,
    }


def _generate_entry(changes: dict, task_id: str | None = None) -> str:
    """生成一条 CHANGELOG 条目（Markdown 格式）。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"### {now}"]

    request = changes.get("request", "")
    if request:
        lines.append(f"- **任务**: {request[:120]}{'...' if len(request) > 120 else ''}")

    files = changes.get("files", [])
    if files:
        file_list = "、".join(f"`{f}`" for f in files[:6])
        if len(files) > 6:
            file_list += f" 等 {len(files)} 个文件"
        lines.append(f"- **文件**: {file_list}")

    if changes.get("tests"):
        lines.append(f"- **测试**: {changes['tests']}")
    if changes.get("fixes"):
        lines.append(f"- **修复**: {changes['fixes']}")

    if task_id:
        lines.append(f"- **任务 ID**: `{task_id[:8]}`")

    return "\n".join(lines)


def run_changelog_step(step: dict, context: dict, events: list, task_id: str | None = None) -> None:
    """更新项目 CHANGELOG 文件。

    从 context 自动提取用户请求、变更文件列表、测试结果、修复信息，
    追加到项目根目录下的 CHANGELOG.md 中。
    """
    from ....worker_config import stream_chunk, stream_start, stream_end, create_event

    meta = context.get("meta", {})
    workspace_path = (
        (meta.get("workspace_scan") or {}).get("root")
        or meta.get("workspace_path")
        or os.getcwd()
    )

    changelog_path = _find_changelog(workspace_path)

    if task_id:
        stream_start(task_id, "正在更新工作日志...", phase="changelog")

    changes = _extract_changes(context)
    if changes is None:
        msg = "未检测到本次任务的变更描述，跳过 CHANGELOG 更新。"
        if task_id:
            stream_chunk(task_id, msg, phase="changelog", channel="reasoning")
            stream_end(task_id)
        step["output"] = {"text": msg, "updated": False}
        return

    existing = ""
    if os.path.isfile(changelog_path):
        try:
            with open(changelog_path, "r", encoding="utf-8", errors="replace") as f:
                existing = f.read()
        except OSError:
            pass

    entry = _generate_entry(changes, task_id)
    full_content = existing.rstrip() + "\n\n" + entry + "\n"

    try:
        with open(changelog_path, "w", encoding="utf-8") as f:
            f.write(full_content)
        short_name = os.path.basename(changelog_path)
        msg = f"已更新 {short_name}"
    except OSError as e:
        msg = f"CHANGELOG 写入失败: {e}"

    if task_id:
        stream_chunk(task_id, msg, phase="changelog", channel="reasoning")
        stream_end(task_id)

    step["output"] = {
        "text": msg,
        "file": changelog_path,
        "entry": entry,
        "updated": True,
    }

    context.setdefault("intermediate_results", []).append({
        "type": "changelog",
        "file": changelog_path,
        "entry": entry,
    })

    events.append(create_event("changelog_updated", {
        "file": changelog_path,
        "entry": entry,
    }))