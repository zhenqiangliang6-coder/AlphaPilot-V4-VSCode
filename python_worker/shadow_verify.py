# -*- coding: utf-8 -*-
"""交付前隔离沙箱自检（Shadow Verification）。

为什么需要它
------------
ShopFlow 跟测里，R6（从零生成订单核心实现）反复出现「模型生成的代码与
它自己生成的测试都不自洽」的失败：
  - `OrderCreate.user_id: int` 但测试传字符串 → 422
  - `relationship("OrderItem")` 引用未定义 ORM 类 → SQLAlchemy 解析失败
  - 代码里混入自然语言 / Markdown → SyntaxError
而 `test` 步骤因 `awaiting_authorization` 被 defer，既有 test→fix→retest
闭环从未执行；这些文件被 Node API 原样写盘，导致 R6–R10 连锁失败。
静态语法门控能抓 SyntaxError，抓不到 422 / 未定义 ORM 类这类运行时错误。

治理边界（不可逾越）
--------------------
  - 不写用户工作区：所有文件只落到 tempfile.TemporaryDirectory()
  - 不执行用户项目命令：只运行本次生成代码自带的 pytest
  - 不改变 awaiting_authorization：写盘仍由 Node API 侧授权

触发范围
--------
  仅「从零生成完整 Python 项目且自带 tests/」的 write_code 任务。
  增量修改轮次（R7–R10）不启用 —— 那需要复制基础工作区快照，属于下一阶段。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

_MAX_REPAIR_ROUNDS = 2
_PYTEST_TIMEOUT = 90
_ERROR_LIMIT = 3000


def should_verify(intent: str, file_ops: list) -> bool:
    """只对「自带测试的从零建项目」任务启用，避免误伤增量修改轮次。"""
    if intent != "write_code":
        return False
    paths = [
        str(op.get("path") or "").replace("\\", "/").lstrip("/")
        for op in (file_ops or [])
    ]
    has_tests = any(
        p.startswith("tests/") and p.endswith(".py") for p in paths
    )
    has_source = any(
        p.endswith(".py") and not p.startswith("tests/") for p in paths
    )
    return has_tests and has_source


def _materialize(file_ops: list, root: Path) -> int:
    """把本次生成的文件写进沙箱，返回写入数量。路径越界一律跳过。"""
    count = 0
    for op in file_ops or []:
        if op.get("op") not in ("create", "update", "modify"):
            continue
        raw = str(op.get("path") or "").replace("\\", "/").strip()
        if raw.startswith("/"):
            # 绝对路径必须拒绝，不能 lstrip 后洗成沙箱内的相对路径
            continue
        rel = raw.lstrip("/")
        parts = [seg for seg in rel.split("/") if seg]
        if not parts or ".." in parts or ":" in parts[0]:
            continue
        content = op.get("content")
        if content is None:
            continue
        target = root.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")
        count += 1
    return count


def _run_pytest(root: Path) -> tuple[bool, str]:
    """在沙箱里跑 pytest，返回 (是否通过, 输出摘要)。"""
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(root),
    }
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--disable-warnings"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=_PYTEST_TIMEOUT,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return False, f"沙箱 pytest 超时（{_PYTEST_TIMEOUT}s）"
    except Exception as e:
        return False, f"沙箱 pytest 启动失败: {type(e).__name__}: {e}"
    if proc.returncode == 5:  # no tests collected —— 视为无需验证
        return True, "沙箱内无测试用例，跳过"
    output = ((proc.stdout or "") + "\n" + (proc.stderr or ""))[-_ERROR_LIMIT:]
    return proc.returncode == 0, output


def _repair_prompt(file_ops: list, error_text: str, user_request: str) -> str:
    blocks = []
    for op in file_ops or []:
        if op.get("op") in ("create", "update", "modify") and op.get("content"):
            blocks.append(f"# FILE: {op['path']}\n{op['content']}\n")
    return (
        "你是代码交付前的最后一道自检修复步骤。以下是本轮生成的全部文件，"
        "以及把它们放进隔离沙箱后运行 pytest 的【真实报错】。\n\n"
        "硬性要求：\n"
        "1. 只修复报错指出的真实问题，禁止重构、禁止新增功能；\n"
        "2. 只输出【需要修改】的文件，用 `# FILE: 相对路径` 开头，"
        "后接该文件完整内容；未修改的文件不要输出；\n"
        "3. 不要输出任何说明文字、Markdown 标题或代码围栏，只输出文件块；\n"
        "4. 每个文件必须是完整、可直接运行的源码，不得混入自然语言说明；\n"
        "5. 严格遵守用户原始请求里的字段、类名、状态码与路径契约。\n\n"
        f"=== 用户原始请求（契约以此为准）===\n{(user_request or '')[:1800]}\n\n"
        f"=== 沙箱 pytest 真实报错 ===\n{error_text[:_ERROR_LIMIT]}\n\n"
        "=== 本轮生成的全部文件 ===\n" + "\n".join(blocks)
    )


def verify_and_repair(context: dict, intent: str) -> dict:
    """交付前自愈。优先走事务式交付闸门（G10.15），无基线时回退隔离沙箱。

    返回结构化证据写入 meta.shadow_verify；`block_delivery=True` 表示
    自检最终失败且工作区有良好基线，调用方必须 FAIL-CLOSED 保留磁盘现状。
    """
    file_ops = context.get("final_file_ops") or []
    result = {"ran": False, "passed": False, "rounds": 0,
              "repaired_files": [], "block_delivery": False}

    # ===== G10.15: 事务式交付闸门（含基础工作区的真实 pytest）=====
    # 旧沙箱只 materialize 本次 file_ops，增量轮次会因缺既有模块假失败；
    # 闸门快照整个工作区后应用交付，验证的是真实的"落盘后会怎样"。
    try:
        from .delivery_gate import gate as _delivery_gate
        g = _delivery_gate(context, intent)
    except Exception as _ge:
        g = {"ran": False, "error": f"{type(_ge).__name__}: {_ge}"}
        print(f"[ShadowVerify] 交付闸门异常，回退隔离沙箱: {g['error']}")
    if g.get("ran"):
        return {
            "ran": True,
            "passed": bool(g.get("passed")),
            "rounds": g.get("rounds", 0),
            "repaired_files": list(g.get("fixes", [])),
            "block_delivery": bool(g.get("block_delivery")),
            "delivery_gate": g,
        }

    # ===== 回退：从零建项目（工作区无既有 tests 基线）的隔离沙箱 =====
    if not should_verify(intent, file_ops):
        return result
    result["ran"] = True

    from .agents.qwen.qwen_api import call_llm
    from .file_ops import parse_fileops_v3

    user_request = context.get("meta", {}).get("user_request") or ""

    for round_no in range(1, _MAX_REPAIR_ROUNDS + 2):
        with tempfile.TemporaryDirectory(prefix="alphapilot-shadow-") as tmp:
            root = Path(tmp)
            if _materialize(file_ops, root) == 0:
                result["passed"] = True
                result["note"] = "无可写入文件，跳过"
                return result
            ok, output = _run_pytest(root)

        result["rounds"] = round_no
        if ok:
            result["passed"] = True
            print(f"[ShadowVerify] 第 {round_no} 轮沙箱 pytest 通过")
            return result
        if round_no > _MAX_REPAIR_ROUNDS:
            result["error"] = output[-_ERROR_LIMIT:]
            print(f"[ShadowVerify] {_MAX_REPAIR_ROUNDS} 轮修复后仍未通过，保留错误证据")
            return result

        print(f"[ShadowVerify] 第 {round_no} 轮沙箱 pytest 失败，发起内部修复")
        try:
            reply = call_llm(
                _repair_prompt(file_ops, output, user_request), temperature=0.1
            )
            patched = {
                str(op.get("path") or ""): op.get("content")
                for op in parse_fileops_v3(reply)
                if op.get("content")
            }
        except Exception as e:
            result["error"] = f"内部修复失败: {type(e).__name__}: {e}"
            return result

        changed = []
        for op in file_ops:
            path = str(op.get("path") or "")
            if path not in patched or patched[path] == op.get("content"):
                continue
            new_content = patched[path]
            # 修复轮次不得把新的语法错误带进交付内容
            if path.endswith(".py"):
                try:
                    compile(new_content, path, "exec")
                except SyntaxError as se:
                    print(f"[ShadowVerify] 拒绝采纳语法错误的修复: {path}: {se}")
                    continue
            op["content"] = new_content
            changed.append(path)
        if not changed:
            result["error"] = "内部修复未产出有效改动"
            result["pytest_error"] = output[-_ERROR_LIMIT:]
            return result
        result["repaired_files"].extend(changed)

    return result
