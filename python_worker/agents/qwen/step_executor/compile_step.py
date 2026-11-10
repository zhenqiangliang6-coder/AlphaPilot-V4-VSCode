# -*- coding: utf-8 -*-
# step_executor/compile_step.py
# ---------------------------------------------------------
# G9: compile 步骤 — 语言工具链统一调度器
#
# 职责:
#   1. 从 context.meta 读 target_language
#   2. 判断文件是否已写入磁盘（已授权）还是 pending（未授权）
#   3. 已授权：调用 language_adapter 执行 install → compile 管线
#   4. 未授权：标记 deferred，等待用户授权文件写入后由 Node API 触发验证
#   5. 编译失败时产出结构化错误信息给 fix_step
#
# 设计原则:
#   - 零 LLM: 纯确定性工具链调用
#   - 复用 LanguageAdapter: 编译/安装逻辑不重复实现
#   - 编译失败不终止任务: 错误信息传递给 fix_step 修复
#   - 授权边界: npm install / pip install 仅在文件已授权写入磁盘后执行
#     (AlphaPilot_OS 原则: 自我进化 ≠ 无限权限)
# ---------------------------------------------------------

import os

from ....language_adapter import get_adapter
from ....worker_config import create_event, stream_chunk, stream_start, stream_end


def _get_pending_lang_files(context, language):
    pending = context.get("final_file_ops") or []
    if not pending:
        return []

    lang_ext_map = {
        "javascript": (".js", ".jsx", ".mjs"),
        "typescript": (".ts", ".tsx", ".js", ".jsx", ".mjs"),
        "python": (".py",),
    }
    exts = lang_ext_map.get(language, (".py",))
    return [f for f in pending if any(f.get("path", "").endswith(ext) for ext in exts)]


def _files_exist_on_disk(workspace_path, language):
    lang_indicators = {
        "javascript": ["package.json", "node_modules"],
        "typescript": ["package.json", "tsconfig.json"],
        "python": ["requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", ".venv"],
    }
    for indicator in lang_indicators.get(language, ["package.json", "requirements.txt"]):
        if os.path.exists(os.path.join(workspace_path, indicator)):
            return True
    return False


def run_compile_step(step, context, events, task_id=None):
    meta = context.get("meta", {})
    language = meta.get("target_language", "python")
    workspace_path = meta.get("workspace_path", "")

    if task_id:
        try:
            stream_start(task_id, "🔨 正在编译项目...", phase="compile")
        except Exception:
            pass

    if not workspace_path or not os.path.isdir(workspace_path):
        msg = "compile: 工作区路径无效，跳过编译验证"
        if task_id:
            stream_chunk(task_id, msg, phase="compile", channel="status")
        step["output"] = {
            "text": msg,
            "compile": {"success": False, "error": "workspace_path not set or invalid", "skipped": True},
        }
        if task_id:
            stream_end(task_id)
        return

    adapter = get_adapter(language)
    if adapter is None:
        msg = f"compile: 不支持的语言 {language}，跳过编译验证"
        if task_id:
            stream_chunk(task_id, msg, phase="compile", channel="status")
        step["output"] = {
            "text": msg,
            "compile": {"success": False, "error": f"unsupported language: {language}", "skipped": True},
        }
        if task_id:
            stream_end(task_id)
        return

    pending_lang_files = _get_pending_lang_files(context, language)
    files_on_disk = _files_exist_on_disk(workspace_path, language)

    if not files_on_disk and pending_lang_files:
        pending_list = [f["path"] for f in pending_lang_files[:8]]
        manifest_hint = ""
        package_json_pending = any(f.get("path", "").endswith("package.json") for f in pending_lang_files)
        if package_json_pending:
            manifest_hint = " (含 package.json)"
        pending_count = len(pending_lang_files)
        msg = (
            f"⏸️  {language} 编译延迟：{pending_count} 个文件待用户授权写入磁盘{manifest_hint}。\n"
            f"   文件列表: {', '.join(pending_list)}\n"
            f"   npm install + 编译将在文件写入后执行。"
        )
        if task_id:
            stream_chunk(task_id, msg, phase="compile", channel="status")

        step["output"] = {
            "text": msg,
            "language": language,
            "compile": {
                "success": False,
                "status": "deferred",
                "reason": "files_pending_authorization",
                "pending_file_count": pending_count,
                "pending_files": pending_list,
                "has_manifest": package_json_pending,
            },
        }
        context.setdefault("pending_verification", {})["compile"] = {
            "language": language,
            "phase": "post_authorization",
            "required": ["install_dependencies", "compile"],
            "dependent_files": pending_list,
        }
        events.append(create_event("tool_completed", {
            "tool": f"compile.{language}",
            "status": "deferred",
            "reason": "files_pending_authorization",
        }))
        if task_id:
            stream_end(task_id)
        return

    if not files_on_disk and not pending_lang_files:
        msg = f"ℹ️  compile: 工作区无 {language} 项目文件且无待写入文件，跳过编译"
        if task_id:
            stream_chunk(task_id, msg, phase="compile", channel="status")
        step["output"] = {
            "text": msg,
            "compile": {"success": False, "skipped": True, "status": "no_files"},
        }
        if task_id:
            stream_end(task_id)
        return

    results = {"install": None, "compile": None}

    if task_id:
        stream_chunk(task_id, f"📦 安装 {language} 依赖...", phase="compile", channel="tool")

    install_result = adapter.install_dependencies(workspace_path)
    results["install"] = install_result.to_dict()

    if install_result.error and not install_result.success:
        if task_id:
            stream_chunk(
                task_id,
                f"⚠️ 依赖安装警告: {install_result.error[:120]}",
                phase="compile",
                channel="status",
            )

    if task_id:
        stream_chunk(task_id, "🔨 运行编译/类型检查...", phase="compile", channel="tool")

    compile_result = adapter.compile(workspace_path)
    results["compile"] = compile_result.to_dict()

    if compile_result.success:
        msg = (
            f"✅ {language} 编译通过 ({compile_result.duration_seconds:.1f}s)"
        )
        if task_id:
            stream_chunk(task_id, msg, phase="compile", channel="status")
    else:
        error_detail = compile_result.stderr or compile_result.error or "编译失败，无详细错误信息"
        msg = (
            f"❌ {language} 编译失败 ({compile_result.duration_seconds:.1f}s)\n"
            f"{error_detail[:2000]}"
        )
        if task_id:
            stream_chunk(task_id, msg, phase="compile", channel="status")

        context.setdefault("intermediate_results", []).append({
            "type": "compile",
            "status": "failed",
            "output": {
                "language": language,
                "error": error_detail[:2000],
                "install_result": results["install"],
                "compile_result": results["compile"],
            },
        })

    output = {
        "text": msg,
        "language": language,
        "install": results["install"],
        "compile": results["compile"],
    }

    step["output"] = output
    events.append(create_event("tool_completed", {
        "tool": f"compile.{language}",
        "status": "completed" if compile_result.success else "failed",
        "compile_result": results["compile"],
    }))

    if task_id:
        stream_end(task_id)