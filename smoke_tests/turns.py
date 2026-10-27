"""Worker turn execution and intent routing for smoke tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

from smoke_tests.config import SCRIPT_DIR
from python_worker.agents.qwen import qwen_worker_v2
from python_worker.file_ops import parse_fileops_v3
from python_worker.memory_integration import MemoryIntegration

TURNS = [
    (
        "Architect",
        "\u8bbe\u8ba1\u4e00\u4e2a Python \u6570\u636e\u5206\u6790\u5de5\u5177\u7bb1\u7684\u7cfb\u7edf\u67b6\u6784",
        "architecture",
        "architect",
        "architect",
    ),
    (
        "Engineer",
        "\u521b\u5efa\u4e00\u4e2a\u7528\u4e8e\u6570\u636e\u52a0\u8f7d\u7684 Python \u6a21\u5757",
        "write_code",
        "engineer",
        "engineer",
    ),
    (
        "Reviewer",
        "\u8bf7\u5ba1\u67e5 src/app.py \u4ee3\u7801\u6709\u6ca1\u6709\u98ce\u9669",
        "code_review",
        "reviewer",
        "reviewer",
    ),
    (
        "Mentor",
        "\u6559\u6211\u5982\u4f55\u4f7f\u7528\u8fd9\u4e2a\u9879\u76ee",
        "mentor_explain",
        "mentor",
        "teacher",
    ),
    (
        "Engineer follow-up",
        "\u5b9e\u73b0\u4e00\u4e2a\u6570\u636e\u53ef\u89c6\u5316\u529f\u80fd",
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


def run_worker_turn(sandbox: Path, prompt: str) -> dict:
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


def exercise_memory_integration() -> bool:
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


def exercise_real_memory_integration(sandbox: Path) -> tuple[bool, str]:
    node_exe = shutil.which("node")
    if not node_exe:
        return False, "\u672a\u627e\u5230 Node.js \u53ef\u6267\u884c\u6587\u4ef6\uff08\u8bf7\u5b89\u88c5 Node.js\uff09"

    repo_root = SCRIPT_DIR
    node_api_dir = repo_root / "node-api"
    test_script = node_api_dir / "test_memory_chain.js"

    if not test_script.is_file():
        return False, f"\u6d4b\u8bd5\u811a\u672c\u7f3a\u5931: {test_script}"

    try:
        proc = subprocess.run(
            [node_exe, str(test_script)],
            cwd=str(node_api_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            env={
                **os.environ,
                "NODE_ENV": "test",
            },
        )
    except subprocess.TimeoutExpired:
        return False, "Node.js \u8bb0\u5fc6\u6d4b\u8bd5\u811a\u672c\u8d85\u65f6\uff0830s\uff09"
    except FileNotFoundError:
        return False, f"Node.js \u4e0d\u53ef\u7528: {node_exe}"

    stderr = (proc.stderr or "").strip()
    stdout = (proc.stdout or "").strip()

    if proc.returncode != 0:
        detail = f"Node.js \u811a\u672c\u975e\u96f6\u9000\u51fa\u7801 {proc.returncode}"
        try:
            result = json.loads(stdout)
            detail = f"{result.get('step', '?')}: {result.get('error', 'unknown')}"
        except (json.JSONDecodeError, KeyError):
            if stderr:
                detail = stderr.split("\n")[-1]
        return False, detail

    try:
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                result = json.loads(line)
                break
        else:
            return False, f"stdout \u4e2d\u672a\u627e\u5230 JSON: {stdout[:200]}"
    except json.JSONDecodeError:
        return False, f"\u65e0\u6cd5\u89e3\u6790\u811a\u672c\u8f93\u51fa: {stdout[:200]}"

    if result.get("ok") is True:
        return True, ""
    else:
        return False, f"{result.get('step', '?')}: {result.get('error', 'unknown')}"