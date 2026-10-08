import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from python_worker.agents.qwen.step_executor import docstring_step


def test_docstring_result_replaces_content_in_final_fileops(monkeypatch):
    documented_code = "def predict(value):\n    \"\"\"Return the input value.\"\"\"\n    return value"
    monkeypatch.setattr(
        docstring_step,
        "call_qwen_with_persona",
        lambda *args, **kwargs: f"```python\n{documented_code}\n```",
    )
    context = {
        "final_file_ops": [{
            "op": "create",
            "path": "src/predictor.py",
            "content": "def predict(value):\n    return value",
        }],
        "meta": {"persona": "engineer", "intent": "refactor"},
        "intermediate_results": [],
    }
    step = {}

    docstring_step.run_docstring_step(step, context, [])

    assert context["final_file_ops"][0]["content"] == documented_code
    assert context["final_file_ops"][0]["from_step"] == "docstring"
    assert "待确认" in step["output"]["text"]


def test_invalid_docstring_output_is_not_added_to_fileops(monkeypatch):
    monkeypatch.setattr(
        docstring_step,
        "call_qwen_with_persona",
        lambda *args, **kwargs: "```python\ndef broken(:\n```",
    )
    original_op = {
        "op": "create",
        "path": "src/predictor.py",
        "content": "def predict(value):\n    return value",
    }
    context = {
        "final_file_ops": [original_op.copy()],
        "meta": {"persona": "engineer", "intent": "refactor"},
        "intermediate_results": [],
    }
    step = {}

    docstring_step.run_docstring_step(step, context, [])

    assert context["final_file_ops"] == [original_op]
    assert "未通过 Python 语法检查" in step["output"]["text"]