import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from python_worker.agents.qwen.step_executor import fix_step


def test_fix_step_writes_valid_fix_to_final_fileops(monkeypatch):
    fixed_code = "import numpy as np\n\nprint(np.array([1, 2]))"
    monkeypatch.setattr(
        fix_step,
        "call_qwen_with_persona",
        lambda *args, **kwargs: f"# FILE: src/cli.py\n```python\n{fixed_code}\n```",
    )
    context = {
        "final_file_ops": [],
        "meta": {
            "intent": "fix_code",
            "persona_config": {"name": "engineer"},
            "source_files": {"src/cli.py": "```python\nprint(np.array([1, 2]))\n```"},
            "user_request": "修复 src/cli.py 的 Python 语法错误",
        },
        "intermediate_results": [],
    }
    step = {}

    fix_step.run_fix_step(step, context, [])

    assert context["final_file_ops"] == [{
        "op": "modify",
        "path": "src/cli.py",
        "content": fixed_code,
        "file_type": "file",
        "language": None,
        "reason": "修复 Python 语法或缩进错误",
        "from_step": "fix",
        "intent": "fix_code",
    }]
    assert "等待确认" in step["output"]["text"]


def test_fix_step_rejects_invalid_python_without_fileops(monkeypatch):
    monkeypatch.setattr(
        fix_step,
        "call_qwen_with_persona",
        lambda *args, **kwargs: "# FILE: src/cli.py\n```python\ndef broken(:\n```",
    )
    context = {
        "final_file_ops": [],
        "meta": {
            "intent": "fix_code",
            "persona_config": {"name": "engineer"},
            "source_files": {"src/cli.py": "broken source"},
            "user_request": "修复 src/cli.py",
        },
        "intermediate_results": [],
    }
    step = {}

    fix_step.run_fix_step(step, context, [])

    assert context["final_file_ops"] == []
    assert step["output"]["file_ops"] == []
    assert "未通过检查" in step["output"]["text"]