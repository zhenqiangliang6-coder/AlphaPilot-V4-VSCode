"""Offline AlphaPilot smoke test using a disposable project sandbox.

This exercises the real Qwen worker routing and policy entry point without
calling an LLM or touching the repository. External services and unsupported
product behavior are reported as gaps rather than simulated as product passes.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from python_worker.agents.qwen import qwen_worker_v2
from python_worker.collaboration_modes import enforce_file_operation_policy
from python_worker.context_builder import inspect_python_project
from python_worker.file_ops import parse_fileops_v3
from python_worker.intent_router import IntentRouter
from python_worker.memory_integration import MemoryIntegration


TURNS = [
    (
        "Architect",
        "设计一个 Python 数据分析工具箱的系统架构",
        "architecture",
        "engineer",
        "teacher",
    ),
    (
        "Engineer",
        "创建一个用于数据加载的 Python 模块",
        "write_code",
        "engineer",
        "engineer",
    ),
    (
        "Reviewer",
        "请审查 src/app.py 代码有没有风险",
        "code_review",
        "engineer",
        "reviewer",
    ),
    (
        "Mentor",
        "教我如何使用这个项目",
        "mentor_explain",
        "mentor",
        "teacher",
    ),
    (
        "Engineer follow-up",
        "实现一个数据可视化功能",
        "write_code",
        "engineer",
        "engineer",
    ),
]

GENERATED_PROTOCOL = """# FILE: src/calculator.py
def add(left, right):
    return left + right

# TEST: tests/test_calculator.py
from src.calculator import add


def test_add():
    assert add(2, 3) == 5

# FILE: src/__init__.py

# DEPENDS: pandas,numpy,openpyxl
"""


def _run_worker_turn(sandbox: Path, prompt: str) -> dict:
    steps_seen = []

    def fake_execute_step(task_id, step, events, context):
        step_type = step["type"]
        steps_seen.append(step_type)
        step["output"] = {"text": f"offline {step_type}"}

        if step_type == "write":
            file_ops = parse_fileops_v3(GENERATED_PROTOCOL)
            context["final_file_ops"] = [
                op for op in file_ops if not op.get("_internal")
            ]
            context["file_ops"] = context["final_file_ops"]
            step["output"]["file_ops"] = context["final_file_ops"]
            step["output"]["text"] = GENERATED_PROTOCOL

        if step_type == "analyze":
            context["final_file_ops"] = [{"path": "must-not-survive.py"}]
            events.append({"data": {"file_ops": [{"path": "must-not-survive.py"}]}})

    context = {
        "final_file_ops": [],
        "intermediate_results": [],
        "tool_outputs": [],
    }
    with (
        patch.object(qwen_worker_v2, "MEMORY_ENABLED", False),
        patch.object(qwen_worker_v2, "check_stop_flag", return_value=False),
        patch.object(qwen_worker_v2, "stream_start"),
        patch.object(qwen_worker_v2, "stream_chunk"),
        patch.object(qwen_worker_v2, "execute_step", side_effect=fake_execute_step),
    ):
        result = qwen_worker_v2.execute_task(
            "qwen_generate",
            {"prompt": prompt, "workspace_path": str(sandbox)},
            f"smoke-{len(prompt)}",
            [],
            [],
            context,
        )

    return {
        "result": result,
        "intent": context["meta"]["intent"],
        "persona": context["meta"]["persona"],
        "mode": context["meta"]["collaboration_mode"],
        "chain": context["meta"]["execution_chain"],
        "deferred": context["meta"].get("deferred_steps", []),
        "file_ops": context.get("final_file_ops", []),
        "steps": steps_seen,
    }


def _apply_file_ops(sandbox: Path, file_ops: list[dict]) -> None:
    root = sandbox.resolve()
    for operation in file_ops:
        relative = Path(operation["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise AssertionError(f"Unsafe sandbox path: {relative}")
        target = (root / relative).resolve()
        target.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(operation.get("content", ""), encoding="utf-8")


def _run_pytest(sandbox: Path) -> subprocess.CompletedProcess[str] | None:
    if importlib.util.find_spec("pytest") is None:
        return None
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=sandbox,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env=env,
        check=False,
    )


def _exercise_memory_integration() -> bool:
    class InMemoryStore:
        def __init__(self):
            self.content = "Earlier project decision: keep data loading in src."

        def build_memory_context(self, user_id, current_query, max_tokens):
            return self.content if "remember" in current_query else ""

    from python_worker import memory_integration

    store = InMemoryStore()
    with patch.object(memory_integration, "get_memory_service", return_value=store):
        context = MemoryIntegration.build_context(
            "smoke-user",
            "turn-2",
            "remember the previous project decision",
        )
        enhanced = MemoryIntegration.enhance_prompt(
            "Add a data visualization module", context
        )
    return (
        context.has_memory
        and "Earlier project decision" in context.memory_context
        and "Earlier project decision" in enhanced
    )


def run() -> bool:
    print("AlphaPilot offline E2E smoke test")
    print(f"Project: {SCRIPT_DIR}")
    results: list[tuple[str, str, str]] = []

    with tempfile.TemporaryDirectory(prefix="AlphaPilot_SmokeTest_") as temp:
        sandbox = Path(temp)
        (sandbox / "src").mkdir()
        (sandbox / "tests").mkdir()
        (sandbox / "src" / "app.py").write_text(
            "def run():\n    return True\n", encoding="utf-8"
        )

        turn_results = []
        for label, prompt, expected_intent, expected_persona, expected_mode in TURNS:
            routed_intent, routed_persona, routed_chain = IntentRouter.detect_intent(prompt)
            assert routed_intent == expected_intent, (label, routed_intent)
            assert routed_persona == expected_persona, (label, routed_persona)

            result = _run_worker_turn(sandbox, prompt)
            assert result["intent"] == expected_intent, (label, result["intent"])
            assert result["persona"] == expected_persona, (label, result["persona"])
            assert result["mode"] == expected_mode, (label, result["mode"])
            assert result["chain"] == routed_chain, (label, result["chain"])
            turn_results.append(result)

        actual_personas = {result["persona"] for result in turn_results}
        if {"architect", "reviewer"}.issubset(actual_personas):
            results.append(("Independent architect/reviewer personas", "PASS", ""))
        else:
            results.append((
                "Dedicated architect/reviewer roles and architecture write",
                "GAP",
                "Architecture routes to engineer persona + teacher mode (its FileOps are cleared); "
                "review uses engineer persona + reviewer mode.",
            ))

        dep_project = sandbox / "dependency-check"
        dep_project.mkdir()
        (dep_project / "requirements.txt").write_text(
            "pandas\nnumpy\n", encoding="utf-8"
        )
        (dep_project / "main.py").write_text(
            "import pandas\nimport numpy\nimport openpyxl\n", encoding="utf-8"
        )
        scan = inspect_python_project(str(dep_project))
        marker_ops = [
            operation
            for operation in parse_fileops_v3(GENERATED_PROTOCOL)
            if operation["op"] == "depends"
        ]
        found_sources = (
            bool(scan["dependency_manifests"])
            and {"pandas", "numpy"}.issubset(scan["inferred_dependencies"])
            and "openpyxl" in scan["unresolved_imports"]
            and marker_ops[0]["data"]["files"] == ["pandas", "numpy", "openpyxl"]
        )
        assert found_sources, "At least one dependency discovery source is unavailable"
        results.append((
            "Dependency sources (manifest, DEPENDS, AST)",
            "GAP",
            "All three signals are detected separately; no product API merges/deduplicates them.",
        ))

        memory_ok = _exercise_memory_integration()
        assert memory_ok, "Memory integration did not retrieve the stored test memory"
        results.append((
            "Cross-turn memory integration",
            "PARTIAL",
            "The real integration wrapper passed with an in-memory provider; PostgreSQL persistence was not exercised.",
        ))

        generated_ops = [
            operation
            for operation in parse_fileops_v3(GENERATED_PROTOCOL)
            if operation.get("path")
        ]
        _apply_file_ops(sandbox, generated_ops)
        pytest_result = _run_pytest(sandbox)
        if pytest_result is None:
            results.append(("Multi-file generation + real pytest", "BLOCKED", "pytest is not installed."))
        else:
            if pytest_result.returncode != 0:
                raise AssertionError(
                    "Sandbox pytest failed:\n"
                    + pytest_result.stdout
                    + pytest_result.stderr
                )
            results.append(("Multi-file FileOps + real pytest fixture", "PASS", ""))
        results.append((
            "Agent-driven test failure self-healing",
            "GAP",
            "The Qwen test step uses fake pytest and has no automatic fix-and-rerun loop.",
        ))

        for label, result in zip((turn[0] for turn in TURNS), turn_results):
            print(
                f"  {label}: intent={result['intent']} persona={result['persona']} "
                f"mode={result['mode']} chain={' -> '.join(result['chain'])}"
            )
        for name, status, detail in results:
            suffix = f" — {detail}" if detail else ""
            print(f"  [{status}] {name}{suffix}")

        review, mentor = turn_results[2], turn_results[3]
        assert review["mode"] == "reviewer" and not review["file_ops"]
        assert mentor["mode"] == "teacher" and not mentor["file_ops"]
        assert "test" in turn_results[1]["deferred"], (
            "Engineer test execution should remain approval-gated."
        )
        results.append(("Read-only review/teaching + test approval gate", "PASS", ""))
        print("  [PASS] Read-only review/teaching + test approval gate")

    gaps = [item for item in results if item[1] in {"GAP", "PARTIAL", "BLOCKED"}]
    print(f"\nResult: {len(results) - len(gaps)} PASS, {len(gaps)} incomplete")
    print("The sandbox was automatically removed; no project files were written.")
    return not gaps


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        raise SystemExit(0 if run() else 1)
    except Exception as error:
        print(f"[FAIL] {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1) from error
