# -*- coding: utf-8 -*-
# step_executor/setup_step.py
# ---------------------------------------------------------
# P2: setup 步骤 — DEPENDS 块处理（确定性, 零 LLM）
#
# 职责:
#   1. 扫描所有 write 步骤输出的 # DEPENDS: 指令
#   2. 解析依赖文件列表, 检查是否存在于 workspace 或待创建列表中
#   3. 缺失文件生成占位 stub（避免后续步骤因文件不存在而报错）
#   4. 检测项目生态, 自动创建/更新清单文件（requirements.txt 等）
#
# 原则:
#   - 零 LLM 依赖: 纯文件系统扫描 + 规则匹配
#   - 幂等性: 已有文件不重复创建
#   - 向后兼容: 无 DEPENDS 块或空 workspace 时, 静默跳过
# ---------------------------------------------------------

import os
import json
from pathlib import Path

from ....file_ops import create_file_op

# ── 包格式 → 清单文件 ────────────────────────────────────
# 每个清单文件描述它的格式规范（JSON 为最小骨架，TOML 为最小节，txt 为空）
_MANIFEST_TEMPLATES = {
    "requirements.txt": "",
    "requirements-dev.txt": "",
    "package.json": '{\n  "name": "app",\n  "private": true,\n  "dependencies": {}\n}',
    "pyproject.toml": '[project]\nname = "app"\nversion = "0.1.0"\n',
    "Gemfile": 'source "https://rubygems.org"\n',
    "composer.json": '{\n  "name": "app/app",\n  "require": {}\n}',
    "go.mod": "module app\n\ngo 1.21\n",
    "Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\nedition = "2021"\n',
}


def _normalize_path(path: str) -> str:
    """统一路径为正斜杠格式."""
    return path.replace("\\", "/")


def _sniff_ecosystem(file_ops: list, ws_root: str, depends_list: list = None) -> set:
    """检测项目使用的技术栈/生态系统.

    从已有 file_ops、workspace 文件和 DEPENDS 声明推测项目生态:
    - ".py" 文件 -> Python (requirements.txt)
    - ".ts/.tsx/.js/.jsx" -> Node.js (package.json)
    - 已有清单文件保留现有格式

    新增 depends_list 参数: setup 阶段 write 尚未执行,
    需从 DEPENDS 声明中提取文件扩展名来补充检测.

    Returns:
        需要确保存在的清单文件相对路径集合.
    """
    manifests = set()

    # 从 file_ops 中检测文件类型
    ext_set = set()
    for op in file_ops:
        path = op.get("path", "")
        if not path or op.get("op") == "delete":
            continue
        ext = Path(path).suffix.lower()
        if ext:
            ext_set.add(ext)
        # 已有清单文件不重复创建
        basename = Path(path).name
        if basename in _MANIFEST_TEMPLATES:
            manifests.add(path)

    # 按扩展名推断需要的清单文件
    if ".py" in ext_set:
        # Python 项目：优先 pyproject.toml，降级到 requirements.txt
        if not any(m.endswith("pyproject.toml") or m.endswith("requirements.txt")
                   for m in manifests):
            manifests.add("requirements.txt")

    if ext_set & {".ts", ".tsx", ".js", ".jsx"}:
        if not any(m.endswith("package.json") for m in manifests):
            manifests.add("package.json")

    # 从 DEPENDS 声明中补充文件扩展名（setup 阶段 write 尚未执行）
    if depends_list:
        for _owner, dep_files in depends_list:
            for df in dep_files:
                ext = Path(df).suffix.lower()
                if ext:
                    ext_set.add(ext)

    # 从 workspace 已有文件补充
    if ws_root and os.path.isdir(ws_root):
        for manifest_name in _MANIFEST_TEMPLATES:
            mpath = os.path.join(ws_root, manifest_name)
            if os.path.isfile(mpath):
                manifests.add(manifest_name)

    return manifests


def _collect_depends_declarations(context: dict) -> list:
    """从 context 中收集所有 DEPENDS 声明.

    数据来源:
    1. context["final_file_ops"] 中 op="depends" 的 FileOp
    2. context["intermediate_results"] 中 write 步骤的 file_ops

    Returns:
        [(depends_path, [file1, file2, ...]), ...]
    """
    all_depends = []

    # 来源 1：final_file_ops 中的 depends ops
    for op in context.get("final_file_ops", []):
        if op.get("op") == "depends":
            files = op.get("data", {}).get("files", [])
            if files:
                # depends ops 没有关联的宿主文件路径，用 "all" 占位
                all_depends.append(("_global_", files))

    # 来源 2：intermediate_results 中的 write 步骤
    for result in context.get("intermediate_results", []):
        if result.get("type") != "write":
            continue
        for op in result.get("file_ops", []):
            if op.get("op") == "depends":
                files = op.get("data", {}).get("files", [])
                if files:
                    all_depends.append((op.get("path", "_unknown_"), files))

    return all_depends


def run_setup_step(step, context, events, task_id=None):
    """
    P2 setup 步骤入口.

    流程:
    1. 收集 DEPENDS 声明
    2. 收集已存在的文件路径（workspace + file_ops）
    3. 找出缺失的文件, 生成占位 stub
    4. 检测生态, 确保清单文件存在
    5. 追加 file_ops 到 context
    """
    file_ops = context.get("final_file_ops", [])
    if not file_ops:
        step["output"] = {"text": "setup: 无 FileOps, 跳过.", "stubs_created": 0}
        return

    ws_root = context.get("meta", {}).get("workspace_path", "")
    new_ops = []
    stubs_created = 0

    # ── 1. 收集 DEPENDS 声明 ──
    depends_list = _collect_depends_declarations(context)

    # ── 2. 收集已存在路径 ──
    existing_paths = set()
    for op in file_ops:
        fp = op.get("path", "")
        if fp and op.get("op") != "delete":
            existing_paths.add(_normalize_path(fp))

    if ws_root and os.path.isdir(ws_root):
        for root, dirs, files in os.walk(ws_root):
            rel_root = os.path.relpath(root, ws_root).replace("\\", "/")
            if rel_root == ".":
                rel_root = ""
            for fname in files:
                rp = f"{rel_root}/{fname}" if rel_root else fname
                # 跳过隐藏文件和虚拟环境
                if "/." in rp or rp.startswith("."):
                    # 但保留 .env 和 .gitignore 等非隐藏目录文件
                    if not fname.startswith("."):
                        continue
                    if fname in (".env", ".env.example", ".gitignore",
                                 ".dockerignore", ".editorconfig"):
                        existing_paths.add(rp)
                    continue
                existing_paths.add(rp)

    # ── 3. 查找缺失依赖文件，生成 stub ──
    missing_files = set()
    for owner_path, dep_files in depends_list:
        for dep in dep_files:
            dep_norm = _normalize_path(dep.strip())
            if dep_norm and dep_norm not in existing_paths:
                missing_files.add(dep_norm)

    for missing in sorted(missing_files):
        # 跳过看起来像包名而非文件名的（无扩展名）
        if "." not in Path(missing).name:
            continue

        ext = Path(missing).suffix.lower()
        stub_content = ""
        stub_reason = f"占位文件（DEPENDS 依赖声明）"

        # 根据扩展名生成合理 stub
        if ext == ".py":
            stub_content = "# TODO: 实现模块\n"
        elif ext in (".ts", ".tsx"):
            stub_content = "// TODO: 实现模块\n"
        elif ext in (".js", ".jsx"):
            stub_content = "// TODO: 实现模块\n"
        elif ext == ".json":
            stub_content = "{}\n"
        elif ext == ".md":
            stub_content = "# TODO\n"

        lang_map = {
            ".py": "python", ".ts": "typescript", ".tsx": "typescriptreact",
            ".js": "javascript", ".jsx": "javascriptreact",
            ".json": "json", ".md": "markdown",
            ".html": "html", ".css": "css",
            ".yaml": "yaml", ".yml": "yaml",
        }

        new_op = create_file_op(
            action="create",
            path=missing,
            content=stub_content,
            file_type="file",
            language=lang_map.get(ext, "plaintext"),
            reason=stub_reason,
            from_step="setup",
        )
        new_op["_internal"] = True
        new_ops.append(new_op)
        existing_paths.add(missing)
        stubs_created += 1

    # ── 4. 检测生态，确保清单文件 ──
    # 从 file_ops 和 depends_list 综合判断是否有代码文件生成
    _code_exts = frozenset({"py", "ts", "tsx", "js", "jsx", "rs", "go", "java"})
    has_code_files = any(
        op.get("path", "").rsplit(".", 1)[-1] in _code_exts
        for op in file_ops
        if op.get("op") in ("create", "modify")
    )
    if not has_code_files and depends_list:
        for _owner, dep_files in depends_list:
            if any(df.rsplit(".", 1)[-1] in _code_exts for df in dep_files):
                has_code_files = True
                break

    if has_code_files:
        manifests = _sniff_ecosystem(file_ops, ws_root, depends_list)
        for manifest_path in sorted(manifests):
            manifest_norm = _normalize_path(manifest_path)
            if manifest_norm in existing_paths:
                continue
            template = _MANIFEST_TEMPLATES.get(
                Path(manifest_norm).name, ""
            )
            new_op = create_file_op(
                action="create",
                path=manifest_norm,
                content=template,
                file_type="file",
                language="plaintext",
                reason="项目清单文件（AlphaPilot 自动补充）",
                from_step="setup",
            )
            new_op["_internal"] = True
            new_ops.append(new_op)
            existing_paths.add(manifest_norm)

    # ── 5. 写入结果 ──
    if new_ops:
        file_ops.extend(new_ops)
        context["final_file_ops"] = file_ops

    step["output"] = {
        "text": (
            f"setup 完成: 生成 {stubs_created} 个依赖占位文件, "
            f"确保 {len(new_ops) - stubs_created} 个清单文件."
        ) if new_ops else "setup: 无需操作.",
        "stubs_created": stubs_created,
        "manifest_files_created": len(new_ops) - stubs_created,
        "file_ops": new_ops,
    }

    if new_ops and task_id:
        from ....worker_config import stream_chunk
        stream_chunk(
            task_id,
            f"\n📦 Setup: {stubs_created} 依赖占位 + "
            f"{len(new_ops) - stubs_created} 清单文件\n",
            phase="setup",
            channel="status",
        )