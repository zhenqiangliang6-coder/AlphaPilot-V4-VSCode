"""Self-healing execution engine: orchestrates test→fix→retest cycles."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from smoke_tests.config import DASHSCOPE_API_KEY, run_pytest_inline
from python_worker.agents.qwen import qwen_worker_v2
from python_worker.agents.qwen.step_executor.fix_step import run_fix_step

FIXED_DIV = (
    "def div(a, b):\n"
    "    if b == 0:\n"
    "        raise ValueError('division by zero')\n"
    "    return a / b\n"
)
UNFIXABLE = "def broken():\n    return undefined_var\n"


def run_single_self_healing_scenario(
    sandbox: Path,
    label: str,
    scenario_prompt: str,
    write_code: str,
    write_content: str,
    test_content: str,
    fix_rounds: int,
    fix_effect: str,
) -> tuple[str, str, str]:
    """Execute a single-file self-healing scenario.

    fix_effect:
      - "always_fix": write FIXED_DIV, verify retest passes
      - "never_fix":  simulate no LLM fix, verify exhaustion exit
      - "real_llm":   call real run_fix_step -> Qwen API, verify end-to-end
    """
    steps_seen = []
    test_call_count = 0
    fix_call_count = 0
    llm_actually_invoked = False

    def layered_execute_step(task_id, step, events, context):
        nonlocal test_call_count, fix_call_count, llm_actually_invoked
        st = step["type"]
        steps_seen.append(st)
        ws = context["meta"].get("workspace_path", str(sandbox))

        if st in ("analyze", "workspace", "plan", "refine", "respond",
                   "doc", "docstring", "profile", "optimize"):
            step["output"] = {"text": f"offline {st}"}
            if st == "analyze":
                events.append({"data": {"file_ops": []}})
            return

        if st == "write":
            src_dir = Path(ws) / "src"
            src_dir.mkdir(parents=True, exist_ok=True)
            (src_dir / write_content).write_text(write_code, encoding="utf-8")
            context["final_file_ops"] = [
                {"path": f"src/{write_content}", "content": write_code}
            ]
            context["file_ops"] = context["final_file_ops"]
            context.setdefault("meta", {})
            context["meta"].setdefault("source_files", {})[
                f"src/{write_content}"
            ] = write_code
            context["meta"].setdefault("intent", "write_code")
            context["meta"].setdefault("workspace_dir", str(ws))
            step["output"] = {"text": write_code, "file_ops": context["final_file_ops"]}
            return

        if st == "test":
            test_call_count += 1
            test_dir = Path(ws) / "tests"
            test_dir.mkdir(parents=True, exist_ok=True)
            test_file = test_dir / f"test_smoke_{test_call_count}.py"
            test_file.write_text(test_content, encoding="utf-8")
            passed, stdout, stderr = run_pytest_inline(
                Path(ws), str(test_file.relative_to(ws))
            )
            step["output"] = {
                "text": f"{stdout}\n{stderr}",
                "exec_success": passed,
                "test_result": {"passed": passed},
            }
            context.setdefault("intermediate_results", []).append({
                "type": "test", "exec_success": passed, "text": stdout + stderr,
                "test_code": test_content,
            })
            return

        if st == "fix":
            fix_call_count += 1
            ws_path = Path(ws)

            if fix_effect == "always_fix" and fix_call_count == 1:
                fixed_code = FIXED_DIV
                src_file = ws_path / "src" / write_content
                src_file.write_text(fixed_code, encoding="utf-8")
                step["output"] = {
                    "text": "self-heal: 1 fix / 1 round",
                    "file_ops": [{"path": f"src/{write_content}", "content": fixed_code}],
                    "fixed_code": fixed_code,
                }
                context.setdefault("intermediate_results", []).append({
                    "type": "fix", "file_ops": step["output"]["file_ops"],
                })
                return

            if fix_effect == "never_fix":
                step["output"] = {"text": "no fix available", "file_ops": []}
                return

            if fix_effect == "real_llm":
                src_path = f"src/{write_content}"
                current_code = (ws_path / src_path).read_text(encoding="utf-8")
                context.setdefault("meta", {})
                context["meta"].setdefault("source_files", {})[src_path] = current_code
                context["meta"].setdefault("intent", "write_code")
                context["meta"].setdefault("workspace_dir", str(ws))
                context["meta"].pop("persona_config", None)

                step_obj = {"type": "fix", "status": "pending", "output": {}}
                try:
                    run_fix_step(step_obj, context, events, task_id=None)
                    llm_actually_invoked = True
                except Exception as exc:
                    step["output"] = {
                        "text": f"LLM fix error: {type(exc).__name__}: {exc}",
                        "file_ops": [],
                    }
                    return

                fix_output = step_obj.get("output", {})
                step["output"] = fix_output
                file_ops = fix_output.get("file_ops", [])
                for op in file_ops:
                    op_path = op.get("path", "")
                    op_content = op.get("content", "")
                    if op_path and op_content:
                        (ws_path / op_path).write_text(op_content, encoding="utf-8")
                        context["meta"]["source_files"][op_path] = op_content
                context.setdefault("intermediate_results", []).append({
                    "type": "fix", "file_ops": file_ops,
                })
                return

    context = {
        "final_file_ops": [],
        "intermediate_results": [],
        "tool_outputs": [],
    }

    if fix_effect == "real_llm" and not DASHSCOPE_API_KEY:
        return "INCOMPLETE", (
            f"{label}: DASHSCOPE_API_KEY not configured, cannot call real LLM"
        )

    with (
        patch.object(qwen_worker_v2, "MEMORY_ENABLED", False),
        patch.object(qwen_worker_v2, "check_stop_flag", return_value=False),
        patch.object(qwen_worker_v2, "stream_start"),
        patch.object(qwen_worker_v2, "stream_chunk"),
        patch.object(qwen_worker_v2, "requires_authorization_before_step", return_value=False),
        patch.object(qwen_worker_v2, "execute_step", side_effect=layered_execute_step),
    ):
        try:
            qwen_worker_v2.execute_task(
                "qwen_generate",
                {"prompt": scenario_prompt, "workspace_path": str(sandbox)},
                f"smoke-heal-{label.replace(' ', '-')}",
                [],
                [],
                context,
            )
        except Exception as exc:
            return "FAIL", f"{label}: Worker threw {type(exc).__name__}: {exc}"

    actual_test = test_call_count
    actual_fix = fix_call_count

    if fix_effect == "always_fix":
        expected_test = 2
        expected_fix = 1
    elif fix_effect == "real_llm":
        expected_test = 2
        expected_fix = 1
    else:
        expected_test = 4
        expected_fix = 4

    if actual_test < expected_test:
        return "FAIL", (
            f"{label}: insufficient test calls (min={expected_test} actual={actual_test}, "
            f"steps={steps_seen})"
        )
    if actual_fix < expected_fix:
        return "FAIL", (
            f"{label}: insufficient fix calls (min={expected_fix} actual={actual_fix}, "
            f"steps={steps_seen})"
        )

    if fix_effect in ("always_fix", "real_llm"):
        passed, stdout, stderr = run_pytest_inline(
            sandbox, f"tests/test_smoke_{actual_test}.py"
        )
        if not passed:
            return "FAIL", (
                f"{label}: final pytest did not pass — LLM={llm_actually_invoked} "
                f"stdout={stdout[:200]} stderr={stderr[:200]}"
            )
        if fix_effect == "real_llm" and not llm_actually_invoked:
            return "FAIL", (
                f"{label}: pytest passed but LLM was never invoked (possible cache hit)"
            )

    detail = (
        f"test={actual_test} fix={actual_fix} LLM={llm_actually_invoked} "
        f"seq={'->'.join(steps_seen)}"
    )
    return "PASS", detail


def run_multi_file_self_healing_scenario(
    sandbox: Path,
    label: str,
    scenario_prompt: str,
    write_files: dict[str, str],
    test_content: str,
    fix_effect: str,
) -> tuple[str, str, str]:
    """Execute a multi-file self-healing scenario.

    Multiple source files + single test file.
    write_files: {"src/xxx.py": code, ...}
    """
    steps_seen = []
    test_call_count = 0
    fix_call_count = 0
    llm_actually_invoked = False

    def layered_execute_step(task_id, step, events, context):
        nonlocal test_call_count, fix_call_count, llm_actually_invoked
        st = step["type"]
        steps_seen.append(st)
        ws = context["meta"].get("workspace_path", str(sandbox))

        if st in ("analyze", "workspace", "plan", "refine", "respond",
                   "doc", "docstring", "profile", "optimize"):
            step["output"] = {"text": f"offline {st}"}
            if st == "analyze":
                events.append({"data": {"file_ops": []}})
            return

        if st == "write":
            src_dir = Path(ws) / "src"
            src_dir.mkdir(parents=True, exist_ok=True)
            file_ops_out = []
            for rel_path, code in write_files.items():
                (src_dir / Path(rel_path).name).write_text(code, encoding="utf-8")
                file_ops_out.append({"path": rel_path, "content": code})
            context["final_file_ops"] = file_ops_out
            context["file_ops"] = file_ops_out
            context.setdefault("meta", {})
            context["meta"].setdefault("source_files", {})
            for op in file_ops_out:
                context["meta"]["source_files"][op["path"]] = op["content"]
            context["meta"].setdefault("intent", "write_code")
            context["meta"].setdefault("workspace_dir", str(ws))
            step["output"] = {
                "text": "multi-file write", "file_ops": file_ops_out,
            }
            return

        if st == "test":
            test_call_count += 1
            test_dir = Path(ws) / "tests"
            test_dir.mkdir(parents=True, exist_ok=True)
            test_file = test_dir / f"test_smoke_{test_call_count}.py"
            test_file.write_text(test_content, encoding="utf-8")
            passed, stdout, stderr = run_pytest_inline(
                Path(ws), str(test_file.relative_to(ws))
            )
            step["output"] = {
                "text": f"{stdout}\n{stderr}",
                "exec_success": passed,
                "test_result": {"passed": passed},
            }
            context.setdefault("intermediate_results", []).append({
                "type": "test", "exec_success": passed, "text": stdout + stderr,
                "test_code": test_content,
            })
            return

        if st == "fix":
            fix_call_count += 1
            ws_path = Path(ws)

            if fix_effect == "real_llm":
                src_dir = ws_path / "src"
                context.setdefault("meta", {})
                context["meta"].setdefault("source_files", {})
                for rel_path in write_files:
                    file_path = src_dir / Path(rel_path).name
                    if file_path.exists():
                        context["meta"]["source_files"][rel_path] = (
                            file_path.read_text(encoding="utf-8")
                        )
                context["meta"].setdefault("intent", "write_code")
                context["meta"].setdefault("workspace_dir", str(ws))
                context["meta"].pop("persona_config", None)

                step_obj = {"type": "fix", "status": "pending", "output": {}}
                try:
                    run_fix_step(step_obj, context, events, task_id=None)
                    llm_actually_invoked = True
                except Exception as exc:
                    step["output"] = {
                        "text": f"LLM fix error: {type(exc).__name__}: {exc}",
                        "file_ops": [],
                    }
                    return

                fix_output = step_obj.get("output", {})
                step["output"] = fix_output
                file_ops = fix_output.get("file_ops", [])

                # Handle LLM returning basename instead of full path
                for op in file_ops:
                    op_path = op.get("path", "")
                    op_content = op.get("content", "")
                    if not op_path or not op_content:
                        continue
                    if not op_path.startswith("src/") and not op_path.startswith("tests/"):
                        for candidate_rel in write_files:
                            if candidate_rel.endswith("/" + op_path):
                                op_path = candidate_rel
                                op["path"] = op_path
                                break
                        else:
                            if (ws_path / "src" / op_path).exists():
                                op_path = "src/" + op_path
                                op["path"] = op_path
                    (ws_path / op_path).write_text(op_content, encoding="utf-8")
                    context["meta"]["source_files"][op_path] = op_content
                context.setdefault("intermediate_results", []).append({
                    "type": "fix", "file_ops": file_ops,
                })
                return

            step["output"] = {"text": "no fix available", "file_ops": []}

    context = {
        "final_file_ops": [],
        "intermediate_results": [],
        "tool_outputs": [],
    }

    if fix_effect == "real_llm" and not DASHSCOPE_API_KEY:
        return "INCOMPLETE", (
            f"{label}: DASHSCOPE_API_KEY not configured, cannot call real LLM"
        )

    with (
        patch.object(qwen_worker_v2, "MEMORY_ENABLED", False),
        patch.object(qwen_worker_v2, "check_stop_flag", return_value=False),
        patch.object(qwen_worker_v2, "stream_start"),
        patch.object(qwen_worker_v2, "stream_chunk"),
        patch.object(qwen_worker_v2, "requires_authorization_before_step", return_value=False),
        patch.object(qwen_worker_v2, "execute_step", side_effect=layered_execute_step),
    ):
        try:
            qwen_worker_v2.execute_task(
                "qwen_generate",
                {"prompt": scenario_prompt, "workspace_path": str(sandbox)},
                f"smoke-heal-{label.replace(' ', '-')}",
                [],
                [],
                context,
            )
        except Exception as exc:
            return "FAIL", f"{label}: Worker threw {type(exc).__name__}: {exc}"

    actual_test = test_call_count
    actual_fix = fix_call_count

    if fix_effect == "real_llm":
        if actual_test < 2 or actual_test > 4:
            return "FAIL", (
                f"{label}: test count out of range (2-4 expected, actual={actual_test}, "
                f"steps={steps_seen})"
            )
        if actual_fix < 1 or actual_fix > 4:
            return "FAIL", (
                f"{label}: fix count out of range (1-4 expected, actual={actual_fix}, "
                f"steps={steps_seen})"
            )

        passed, stdout, stderr = run_pytest_inline(
            sandbox, f"tests/test_smoke_{actual_test}.py"
        )
        if not passed:
            return "FAIL", (
                f"{label}: final pytest did not pass — LLM={llm_actually_invoked} "
                f"stdout={stdout[:200]} stderr={stderr[:200]}"
            )
        if not llm_actually_invoked:
            return "FAIL", (
                f"{label}: pytest passed but LLM was never invoked (possible cache hit)"
            )

    return "PASS", (
        f"test={actual_test} fix={actual_fix} LLM={llm_actually_invoked} "
        f"seq={'->'.join(steps_seen)}"
    )