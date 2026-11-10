# -*- coding: utf-8 -*-
# step_runner.py
# ---------------------------------------------------------
# Step Runner — 步骤执行循环 + 收尾
#
# Responsibility:
#   - 逐步执行 execution_chain 中的步骤
#   - test→fix→retest 闭环（最多 3 轮）
#   - vision_analysis 跳过（已在 Post-Vision 阶段执行）
#   - 文件操作策略执行
#   - 自清理：追踪生成文件
#   - Python 包完整性：自动补充 __init__.py（P0 确定性后处理）
#
# Extracted from qwen_worker_v2.py execute_task()
# ---------------------------------------------------------

import json
import re
import time
from pathlib import Path

from ...worker_config import redis, check_stop_flag, stream_chunk
from ...intent_router import requires_authorization_before_step
from ...file_ops import track_generated_files, create_file_op
from ...task_state_contract import (
    STEP_STATE_PENDING,
    STEP_STATE_RUNNING,
    STEP_STATE_COMPLETED,
    STEP_STATE_FAILED,
    STEP_STATE_AWAITING_AUTHORIZATION,
    STEP_STATE_SKIPPED,
)

from .step_executor import execute_step
from .step_executor.test_step import discover_project_test_commands

MAX_FIX_RETRIES = 3


def run_execution_loop(
    steps: list,
    execution_plan: dict,
    task_id: str,
    events: list,
    context: dict,
    intent: str,
    mode: str,
):
    """逐步执行 steps 中的步骤，含 test→fix→retest 闭环。

    Returns:
        test_fixed_in_loop: True 如果修复循环已通过测试
    """
    test_fixed_in_loop = False

    for step_index, step in enumerate(steps):
        try:
            if requires_authorization_before_step(execution_plan, step.get("type", "")):
                # P1: 确定性测试命令发现 — 在授权前自动注入，不依赖 LLM plan 输出
                _inject_discovered_test_command(context)
                _defer_test_for_authorization(step, context)
                _skip_remaining_steps(
                    steps,
                    step_index + 1,
                    "等待用户授权并完成项目测试后再继续。",
                )
                break

            if check_stop_flag(task_id):
                step["status"] = STEP_STATE_FAILED
                step["output"] = {"text": "任务已被用户取消"}
                raise Exception("任务已被用户取消")

            # v3.3: 如果 test 已在修复循环中通过，跳过后续 fix
            if test_fixed_in_loop and step.get("type") == "fix":
                step["status"] = STEP_STATE_SKIPPED
                step["reason"] = "测试已在修复循环中通过，跳过重复 fix 步骤"
                step["output"] = {"text": "测试已在修复循环中通过，跳过后继 fix。"}
                test_fixed_in_loop = False
                continue

            # v4.4: vision_analysis 已在 Post-Vision 阶段执行，跳过
            if context.get("_vision_result") and step.get("type") == "vision_analysis":
                step["status"] = STEP_STATE_SKIPPED
                step["reason"] = "视觉分析已在 Post-Vision 阶段预先执行"
                step["output"] = context.get("_vision_result_last_output") or {
                    "text": "视觉分析已在上一阶段完成"
                }
                continue

            step["status"] = STEP_STATE_RUNNING

            # v4.3: 将视觉分析结果注入下游步骤 prompt
            if context.get("_vision_result") and step.get("type") != "vision_analysis":
                step.setdefault("input", {})["prompt"] = (
                    f"[图片分析结果]\n{context['_vision_result']}\n\n"
                    f"---\n\n[用户原始请求]\n{step.get('input', {}).get('prompt', '')}\n\n"
                    f"以上分析结果作为参考，请基于用户请求直接回答。"
                )

            # v3.5: 智能验证治理 — Shadow Mode 影响分析
            # 在 test 步骤执行前分析 final_file_ops 变更，
            # 输出 impact_profile 到 context.meta 供审计。
            # 不改变任何现有测试执行行为。
            if step.get("type") == "test":
                try:
                    from .step_executor.verification_governor import VerificationGovernor
                    _vg = VerificationGovernor(context)
                    context["meta"]["verification_governance"] = _vg.analyze_impact()
                except Exception as _vg_err:
                    context["meta"]["verification_governance"] = {
                        "mode": "shadow",
                        "error": str(_vg_err),
                        "analysis_failed": True,
                    }

            execute_step(task_id, step, events, context)
            step["status"] = STEP_STATE_COMPLETED

            # v3.3: test→fix→retest 闭环
            if step.get("type") == "test":
                test_output = step.get("output", {})
                if test_output.get("exec_success") is True:
                    continue

                if test_output.get("exec_success") is False and _has_executable_test_failure(test_output):
                    _fixed = _run_fix_retest_loop(
                        task_id, events, context, step,
                    )
                    if _fixed:
                        test_fixed_in_loop = True
                    else:
                        _mark_validation_failed(
                            context,
                            step,
                            "测试未通过，修复重测未能验证成功；已停止后续步骤。",
                        )
                        _skip_remaining_steps(
                            steps,
                            step_index + 1,
                            "前置测试未通过。",
                        )
                        break
                else:
                    _mark_validation_failed(
                        context,
                        step,
                        "没有获得明确的测试执行成功证据；不会将此步骤报告为通过。",
                    )
                    _skip_remaining_steps(
                        steps,
                        step_index + 1,
                        "测试结果缺失或测试命令未能执行。",
                    )
                    break

        except Exception as step_error:
            msg = str(step_error)
            if "取消" in msg or "cancel" in msg.lower():
                step["status"] = STEP_STATE_FAILED
                step["output"] = {"text": "任务已被用户取消"}
            else:
                step["status"] = STEP_STATE_FAILED
                step["output"] = {"text": f"步骤执行失败：{step_error}"}
            raise step_error

    return test_fixed_in_loop


def _inject_discovered_test_command(context: dict) -> None:
    """P1: 若 plan LLM 未发现测试命令，通过确定性文件扫描自动补充。"""
    meta = context.setdefault("meta", {})
    
    if meta.get("proposed_test_command"):
        return

    ws = meta.get("workspace_path") or meta.get("workspace_dir") or ""
    if not ws:
        return

    discovered = discover_project_test_commands(ws)
    if discovered:
        meta["proposed_test_command"] = discovered[0]["command"]
        meta["test_discovery"] = {
            "found": True,
            "command": discovered[0]["command"],
            "language": discovered[0]["language"],
            "source": discovered[0]["source"],
            "all_commands": [d["command"] for d in discovered],
        }
        print(f"[STEP_RUNNER] 确定性发现测试命令: {discovered[0]['command']} ({discovered[0]['source']})")


def _defer_test_for_authorization(step: dict, context: dict) -> None:
    meta = context.setdefault("meta", {})
    command = meta.get("proposed_test_command")
    step["status"] = STEP_STATE_AWAITING_AUTHORIZATION
    step["output"] = {
        "text": "项目测试需用户明确授权；当前未运行测试。",
        "proposed_command": command,
        "exec_success": None,
    }
    meta["execution_state"] = "awaiting_authorization"
    deferred_steps = meta.setdefault("deferred_steps", [])
    if "test" not in deferred_steps:
        deferred_steps.append("test")

    requests = meta.setdefault("authorization_requests", [])
    if not any(request.get("type") == "test" for request in requests):
        requests.append({
            "type": "test",
            "command": command,
            "status": "awaiting_host_policy",
        })


def _skip_remaining_steps(steps: list, start_index: int, reason: str) -> None:
    for pending_step in steps[start_index:]:
        if pending_step.get("status") == STEP_STATE_PENDING:
            pending_step["status"] = STEP_STATE_SKIPPED
            pending_step["reason"] = reason
            pending_step["output"] = {"text": reason}


def _has_executable_test_failure(test_output: dict) -> bool:
    result = test_output.get("test_result")
    if not isinstance(result, dict):
        return False
    exit_code = result.get("exit_code")
    return (
        isinstance(exit_code, int)
        and exit_code != 0
        and not result.get("timed_out", False)
    )


def _mark_validation_failed(context: dict, step: dict, message: str) -> None:
    step["status"] = STEP_STATE_FAILED
    output = step.setdefault("output", {})
    output["text"] = f"{output.get('text', '').rstrip()}\n{message}".strip()
    context.setdefault("meta", {})["execution_state"] = "validation_failed"


def _run_fix_retest_loop(task_id: str, events: list, context: dict, test_step: dict) -> bool:
    """test→fix→retest 闭环，最多 3 轮。"""
    for retry in range(1, MAX_FIX_RETRIES + 1):
        if task_id:
            stream_chunk(
                task_id,
                f"\n🔄 测试失败，第 {retry}/{MAX_FIX_RETRIES} 次尝试修复并重测...\n",
            )

        if check_stop_flag(task_id):
            test_step["status"] = STEP_STATE_FAILED
            test_step["output"] = {"text": "任务已被用户取消（测试修复循环中）"}
            raise Exception("任务已被用户取消")

        fix_step = {"type": "fix", "status": STEP_STATE_PENDING, "output": {}}
        try:
            execute_step(task_id, fix_step, events, context)
        except Exception as fe:
            if task_id:
                stream_chunk(task_id, f"修复步骤异常: {fe}")
            _mark_validation_failed(
                context,
                test_step,
                f"修复步骤执行失败：{fe}",
            )
            break

        retest_step = {"type": "test", "status": STEP_STATE_PENDING, "output": {}}
        try:
            execute_step(task_id, retest_step, events, context)
        except Exception as re:
            if task_id:
                stream_chunk(task_id, f"重测步骤异常: {re}")
            _mark_validation_failed(
                context,
                test_step,
                f"重测步骤执行失败：{re}",
            )
            break

        if retest_step.get("output", {}).get("exec_success") is True:
            test_step["output"] = retest_step["output"]
            test_step["status"] = STEP_STATE_COMPLETED
            if task_id:
                stream_chunk(task_id, f"✅ 第 {retry} 次修复后测试通过！\n")
            return True
        elif retry >= MAX_FIX_RETRIES:
            test_step["output"] = retest_step["output"]
            _mark_validation_failed(
                context,
                test_step,
                f"{MAX_FIX_RETRIES} 次修复后测试仍未通过。",
            )
            if task_id:
                stream_chunk(task_id, f"❌ {MAX_FIX_RETRIES} 次修复后测试仍未通过。\n")

    if test_step.get("status") != STEP_STATE_FAILED:
        _mark_validation_failed(
            context,
            test_step,
            "测试修复循环未能产生通过证据。",
        )
    return False


def _store_authorization_in_redis(context: dict, task_id: str):
    """R6 安全契约：存储授权数据到 Redis 供 Node.js 执行端独立验证。

    Worker = 真相：只有 Worker 创建授权条目。
    Node.js 只读验证，不修改 task_state。
    """
    if not task_id:
        return
    authorization_requests = context.get("meta", {}).get("authorization_requests")
    if not authorization_requests:
        return
    auth_key = f"auth:{task_id}"
    auth_data = {
        "task_id": task_id,
        "workspace_path": context.get("meta", {}).get("workspace_path", ""),
        "authorizations": authorization_requests,
        "created_at": time.time(),
        "expires_at": time.time() + 3600,
    }
    try:
        redis.set(auth_key, json.dumps(auth_data, ensure_ascii=False), ex=3600)
    except Exception:
        pass


def _ensure_python_package_inits(file_ops: list) -> int:
    """确定性后处理：为 Python 包目录自动补充 __init__.py

    原则：
    - 零 LLM 依赖，纯文件路径解析
    - 已有 __init__.py 的目录不重复创建
    - 仅在 ws_root 非空时生效（有工作区才有意义）
    - 生成的 FileOp 标记 _internal=True，不出现在用户界面

    Returns:
        创建的 __init__.py 数量
    """
    create_ops = [
        op for op in file_ops
        if op.get("op") in ("create", "modify")
    ]
    if not create_ops:
        return 0

    existing_paths = {
        op["path"] for op in file_ops
        if op.get("path") and op.get("op") != "delete"
    }

    init_paths_needed = set()
    for op in create_ops:
        path = op.get("path", "")
        if not path.endswith(".py"):
            continue
        parts = Path(path).parent.parts
        for i in range(1, len(parts) + 1):
            pkg_path = str(Path(*parts[:i]) / "__init__.py").replace("\\", "/")
            if pkg_path != path and pkg_path not in existing_paths:
                init_paths_needed.add(pkg_path)

    count = 0
    for init_path in sorted(init_paths_needed):
        file_ops.append(create_file_op(
            action="create",
            path=init_path,
            content="",
            file_type="file",
            language="python",
            reason="Python 包初始化文件（AlphaPilot 自动补充）",
            from_step="workspace",
        ))
        existing_paths.add(init_path)
        count += 1

    return count


def finalize_task(
    context: dict,
    steps: list,
    events: list,
    mode: str,
    intent: str,
    payload: dict,
    task_id: str = "",
) -> dict:
    """执行任务收尾：文件策略、自清理追踪、授权请求。

    Returns:
        last_output_text (str)
    """
    from ...collaboration_modes import enforce_file_operation_policy

    enforce_file_operation_policy(context, mode, steps=steps, events=events)

    # v3.2 自清理：追踪本次生成的文件供下次清理
    ws_root = context.get("meta", {}).get("workspace_path", "")
    if ws_root and intent in ("write_code", "fix_code", "refactor", "workspace_maintenance"):
        track_generated_files(redis, ws_root, context["final_file_ops"])
        track_paths = [
            op["path"] for op in context["final_file_ops"]
            if op.get("path") and op.get("op") in ("create", "modify", "test", "doc")
            and not op.get("_internal", False)
        ]
        if track_paths:
            context["final_file_ops"].append(create_file_op(
                "create", ".alphapilot_generated.mark",
                content=json.dumps(sorted(track_paths), ensure_ascii=False, indent=2),
                reason="AlphaPilot 生成文件清单", from_step="workspace",
            ))

    # P0: Python 包完整性 — 自动补充 __init__.py（确定性后处理，零 LLM 依赖）
    if ws_root:
        init_count = _ensure_python_package_inits(context["final_file_ops"])
        if init_count > 0:
            print(f"   📦 Python 包完整性: 自动补充 {init_count} 个 __init__.py")

    # R6 安全契约：为所有文件操作类型生成授权请求
    # CREATE / MODIFY / DELETE / TEST / DOC 均需授权，由 Node.js 独立验证
    op_types = ("create", "modify", "delete", "test", "doc")
    for op_type in op_types:
        matching = [
            op.get("path")
            for op in context.get("final_file_ops", [])
            if op.get("op") == op_type and not op.get("_internal", False)
        ]
        if matching:
            context["meta"].setdefault("authorization_requests", []).append({
                "type": op_type,
                "paths": matching,
                "status": "awaiting_host_policy",
            })

    if context["meta"].get("authorization_requests"):
        context["meta"]["execution_state"] = "awaiting_authorization"

    # R6 安全契约：将授权请求写入 Redis 供 Node.js 执行端独立验证
    _store_authorization_in_redis(context, task_id)

    # ===== v3.4: 语法错误最终门控 =====
    # 在任务标记为完成前，对所有 final_file_ops 中的 Python 文件执行
    # 编译检查。如果 write_step 的语法门控未生效（降级路径或通过
    # fix_step 重新写入时未重新校验），此门控作为最后防线拦截。
    _final_compile_errors = []
    for _fop in context.get("final_file_ops", []):
        _fpath = _fop.get("path") or ""
        _fcontent = _fop.get("content") or ""
        if _fpath.endswith(".py") and _fcontent and not _fop.get("_internal"):
            try:
                compile(_fcontent, _fpath, "exec")
            except SyntaxError as _fse:
                _fop["_compile_error"] = str(_fse)
                _fop["_needs_fix"] = True
                _final_compile_errors.append(f"{_fpath}: {_fse}")
    if _final_compile_errors:
        print(
            f"[WARN] finalize_task: {len(_final_compile_errors)} Python "
            f"文件存在语法错误（已标记 _needs_fix，但任务将继续发布）"
        )
        context["meta"]["_final_compile_errors"] = _final_compile_errors

    # ===== v3.5: 格式污染检测 =====
    # 确定性检查 Python 文件中是否混入了 LLM 步骤标记
    # （refine: / test: / write: / fix: / plan: / analyze:）
    # 这些标记如果出现在非注释/非字符串行，会导致 SyntaxError，
    # 但有些可能被 Python 当作合法声明侥幸通过编译。
    # 本检查作为编译门控的补充防线，捕获编译可过但语义污染的 case。
    _STEP_MARKERS = re.compile(
        r'^\s*(refine|test|write|fix|plan|analyze|execute|respond):',
        re.IGNORECASE
    )
    _pollution_errors = []
    for _fop in context.get("final_file_ops", []):
        _fpath = _fop.get("path") or ""
        _fcontent = _fop.get("content") or ""
        if not _fpath.endswith(".py") or not _fcontent or _fop.get("_internal"):
            continue
        for _li, _line in enumerate(_fcontent.splitlines(), 1):
            _m = _STEP_MARKERS.match(_line)
            if _m:
                _pollution_errors.append(
                    f"{_fpath}:{_li}: 格式污染 — 步骤标记 '{_m.group(1)}:' 出现在代码中"
                )
    if _pollution_errors:
        print(
            f"[WARN] finalize_task: {len(_pollution_errors)} 个格式污染"
            f"（步骤标记混入代码文件）"
        )
        context["meta"]["_format_pollution"] = _pollution_errors
        # 不阻断发布——错误标记已写入 FileOps，
        # 下游（test_step 全量 pytest / Node API 通知）可据此告警

    # P2-6: 标记 context 为终止
    context["_task_terminated"] = True

    return steps[-1].get("output", {}).get("text", "") if steps else ""