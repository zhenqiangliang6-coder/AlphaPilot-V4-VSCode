# -*- coding: utf-8 -*-
# fix_step.py — v3.2
# 统一 fix 链路：集成 self_healing_adapter 提供多层自愈（规则引擎 + LLM + 停滞检测）

import os, subprocess, sys

from .utils import extract_code
from .prompts import fix_prompt
from ....file_ops import parse_fileops_v3, create_file_op
from ....worker_config import stream_start, stream_chunk, stream_end
from ..qwen_api import call_qwen_with_persona, call_qwen
from ....self_healing_adapter import run_healing_fix


def _get_test_context(context):
    """
    从 context 中提取测试相关信息（错误信息 + 测试代码）
    返回: (error_info: str, test_code: str)
    """
    ctx = context or {}
    intermediate = ctx.get("intermediate_results", [])
    test_errors = []
    test_code = ""

    for item in intermediate:
        if item.get("type") != "test":
            continue

        # 提取错误信息
        if isinstance(item, dict) and item.get("status") == "failed":
            test_errors.append(item.get("error", ""))
        output = item.get("output", {})
        if isinstance(output, dict):
            text = output.get("text", "")
            if text:
                test_errors.append(text)

        # ⭐ 新增：提取测试代码
        item_test_code = item.get("test_code", "")
        if item_test_code:
            test_code = item_test_code  # 取最新的测试代码

    error_info = "\n".join(test_errors) if test_errors else ""
    return error_info, test_code


def _get_source_files_from_context(context):
    ctx = context or {}
    meta = ctx.get("meta", {})
    source_files = meta.get("source_files", {})
    if source_files:
        return source_files
    intent = meta.get("intent", "")
    if intent in ("write_code", "refactor", "explain_and_fix"):
        final_ops = ctx.get("final_file_ops") or ctx.get("file_ops", [])
        result = {}
        for op in final_ops:
            path = op.get("path")
            content = op.get("content")
            if path and content:
                result[path] = content
        if result:
            return result
    return {}


def _dedup_merge_file_ops(context, new_ops):
    ctx = context or {}
    if not new_ops:
        return
    changed = {op.get("path") for op in new_ops if op.get("path")}
    existing = ctx.get("final_file_ops") or ctx.get("file_ops", [])
    merged = [op for op in existing if op.get("path") not in changed]
    merged.extend(new_ops)
    ctx["final_file_ops"] = merged
    ctx["file_ops"] = merged


def run_fix_step(
    step,
    context,
    events,
    task_id=None,
    llm_client=None,
    file_parser=None,
    python_compiler=None
):
    if task_id:
        stream_start(task_id, "fix...", phase="fix")

    meta = context.get("meta", {}) if context else {}
    persona = meta.get("persona_config")
    intent = meta.get("intent", "fix_code")
    source_files = _get_source_files_from_context(context)
    error_info, test_code = _get_test_context(context)

    if not error_info:
        error_info = (
            context.get("last_error", "")
            or meta.get("workspace_report", "")
            or meta.get("user_request", "")
        )

    if not source_files:
        if intent == "workspace_maintenance":
            scan = meta.get("workspace_scan", {})
            step["output"] = {
                "text": "fix：",
                "file_ops": [],
                "issues": scan.get("issues", []),
            }
            if task_id:
                stream_end(task_id)
            return
        step["output"] = {
            "text": "fix：未找到可修复的源代码。",
            "file_ops": [],
        }
        if task_id:
            stream_end(task_id)
        return

    project_dir = meta.get("workspace_dir", os.getcwd())

    # ====== v3.2: 判断是否触发自愈引擎 ======
    has_test_error = any(
        kw in (error_info or "").lower()
        for kw in ["error", "fail", "not found", "not defined", "syntax", "assertion"]
    )

    if has_test_error and len(source_files) >= 1:
        # ── 自愈引擎路径 ──
        if task_id:
            stream_chunk(task_id, "检测到测试错误，启动多层自愈引擎...")

        test_output = error_info

        raw_llm = call_qwen_with_persona if persona else call_qwen

        def llm_call_fn(prompt):
            return raw_llm(prompt, persona, use_stream=False) if persona else raw_llm(prompt)

        try:
            heal_result = run_healing_fix(
                source_files=source_files,
                error_info=error_info,
                test_output=test_output,
                project_dir=project_dir,
                llm_call_fn=llm_call_fn,
                max_rounds=5,
            )
        except Exception as e:
            if task_id:
                stream_chunk(task_id, f"自愈引擎异常: {e}，回退到单次修复")
            heal_result = None

        if heal_result and heal_result.get('fixes'):
            file_ops = []
            for fp, content in heal_result.get('fixed_files', {}).items():
                if fp in source_files and content != source_files[fp]:
                    file_ops.append(
                        create_file_op("modify", fp, content,
                                       reason="heal", from_step="fix", intent=intent)
                    )

            step["output"] = {
                "text": f"自愈: {len(heal_result['fixes'])} 个修复 / {heal_result['rounds']} 轮",
                "file_ops": file_ops,
                "fixed_code": file_ops[0]["content"] if len(file_ops) == 1 else "",
                "heal_rounds": heal_result['rounds'],
                "heal_fixes": heal_result['fixes'],
            }
            if context is not None:
                context.setdefault("intermediate_results", []).append(
                    {"type": "fix", "file_ops": file_ops, "heal_rounds": heal_result['rounds']}
                )
            if task_id:
                stream_end(task_id)
            return

    # ── 传统单次 LLM 修复（fallback） ──
    file_ops = []
    errors = []

    for path, original_code in source_files.items():
        prompt = fix_prompt(path, original_code, error_info, test_code)
        try:
            if llm_client is not None:
                response = llm_client.call(prompt)
            else:
                if persona:
                    response = call_qwen_with_persona(prompt, persona, use_stream=False)
                else:
                    response = call_qwen(prompt)

            if file_parser is not None:
                parsed_ops = file_parser.parse(response)
            else:
                parsed_ops = parse_fileops_v3(response)

            parsed_op = next(
                (item for item in parsed_ops if item.get("path") == path), None
            )
            fixed_code = (
                parsed_op.get("content", "")
                if parsed_op
                else extract_code(response)
            )
            if not fixed_code:
                raise ValueError("fix：fix返回空")
            if path.endswith(".py"):
                if python_compiler is not None:
                    python_compiler.compile(fixed_code, path, "exec")
                else:
                    compile(fixed_code, path, "exec")
            if fixed_code == original_code:
                continue
            file_ops.append(
                create_file_op(
                    "modify", path, fixed_code,
                    reason="fix", from_step="fix", intent=intent,
                )
            )
        except Exception as error:
            errors.append(f"{path}: {error}")

    _dedup_merge_file_ops(context, file_ops)

    if file_ops and meta.get("collaboration_mode") == "engineer":
        status_text = f"{len(file_ops)} fix:VS Code"
    elif file_ops:
        status_text = f"{len(file_ops)} fix:"
    else:
        status_text = "fix:"

    if errors:
        status_text += "\n" + "\n".join(errors)

    step["output"] = {
        "text": status_text,
        "file_ops": file_ops,
        "fixed_code": file_ops[0]["content"] if len(file_ops) == 1 else "",
    }
    if context is not None:
        context.setdefault("intermediate_results", []).append(
            {"type": "fix", "file_ops": file_ops, "errors": errors}
        )

    if task_id:
        stream_end(task_id)