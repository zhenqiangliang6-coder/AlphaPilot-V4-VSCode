import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from python_worker.agents.qwen import qwen_worker_v2
from python_worker.agents.qwen.step_executor import workspace_step


def test_workspace_maintenance_reads_files_and_routes_to_fix_and_workspace_tools(tmp_path, monkeypatch):
    source = tmp_path / "src" / "broken.py"
    source.parent.mkdir()
    source.write_text("def broken(:\n    pass\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("sample-package\n", encoding="utf-8")
    executed_steps = []

    monkeypatch.setattr(qwen_worker_v2, "MEMORY_ENABLED", False)
    monkeypatch.setattr(qwen_worker_v2, "check_stop_flag", lambda _task_id: False)
    monkeypatch.setattr(qwen_worker_v2, "stream_start", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(qwen_worker_v2, "stream_chunk", lambda *_args, **_kwargs: None)

    def fake_execute_step(_task_id, step, _events, context):
        executed_steps.append(step["type"])
        step["output"] = {"text": f"{step['type']} completed"}
        if step["type"] == "fix":
            context["final_file_ops"] = []

    monkeypatch.setattr(qwen_worker_v2, "execute_step", fake_execute_step)
    context = {"final_file_ops": [], "intermediate_results": [], "tool_outputs": []}
    result = qwen_worker_v2.execute_task(
        "qwen_generate",
        {
            "prompt": "读取项目文件检查项目里的代码文件语法和缩进错误并修改，创建虚拟环境.vnev并安装项目所需的第三方相关库",
            "workspace_path": str(tmp_path),
        },
        "test-workspace-task",
        [],
        [],
        context,
    )

    assert executed_steps == ["analyze", "fix", "workspace"]
    assert context["meta"]["source_files"] == {
        "src/broken.py": "def broken(:\n    pass\n"
    }
    assert context["meta"]["project_context_files"] == [
        "src/broken.py",
        "requirements.txt",
    ]
    assert context["meta"]["collaboration_mode"] == "engineer"
    assert "docstring" not in context["meta"]["execution_chain"]
    assert result == "workspace completed"


def test_automatic_routes_control_context_write_scope_and_authorized_steps(tmp_path, monkeypatch):
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("def run():\n    return True\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Usage\nRun `python -m app`.\n", encoding="utf-8")
    executed_steps = []

    monkeypatch.setattr(qwen_worker_v2, "MEMORY_ENABLED", False)
    monkeypatch.setattr(qwen_worker_v2, "check_stop_flag", lambda _task_id: False)
    monkeypatch.setattr(qwen_worker_v2, "stream_start", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(qwen_worker_v2, "stream_chunk", lambda *_args, **_kwargs: None)

    def fake_execute_step(_task_id, step, _events, context):
        step_type = step["type"]
        executed_steps.append(step_type)
        step["output"] = {"text": f"{step_type} completed"}
        if step_type == "fix":
            context["final_file_ops"] = [{
                "op": "modify",
                "path": "src/app.py",
                "content": "def run():\n    return False\n",
            }]

    monkeypatch.setattr(qwen_worker_v2, "execute_step", fake_execute_step)

    def execute(prompt):
        executed_steps.clear()
        context = {"final_file_ops": [], "intermediate_results": [], "tool_outputs": []}
        result = qwen_worker_v2.execute_task(
            "qwen_generate",
            {"prompt": prompt, "workspace_path": str(tmp_path)},
            "test-auto-route",
            [],
            [],
            context,
        )
        return result, context, list(executed_steps)

    _, poem_context, poem_steps = execute("帮我定一首关于秋天的诗")
    assert poem_context["meta"]["intent"] == "creative_writing"
    assert poem_context["meta"]["collaboration_mode"] == "creative"
    assert poem_context["meta"]["project_context_files"] == []
    assert poem_context["final_file_ops"] == []
    assert poem_steps == ["analyze", "plan", "write", "refine"]

    _, usage_context, usage_steps = execute("教我如何使用这个项目")
    assert usage_context["meta"]["intent"] == "mentor_explain"
    assert usage_context["meta"]["collaboration_mode"] == "teacher"
    assert "README.md" in usage_context["meta"]["project_context_files"]
    assert usage_context["final_file_ops"] == []
    assert usage_steps == ["analyze", "plan", "respond"]

    _, repair_context, repair_steps = execute(
        "你帮我看看 src/app.py 这个错误是什么，并帮我解决"
    )
    assert repair_context["meta"]["intent"] == "explain_and_fix"
    assert repair_context["meta"]["collaboration_mode"] == "engineer"
    assert repair_context["meta"]["source_files"] == {
        "src/app.py": "def run():\n    return True\n"
    }
    assert [operation["path"] for operation in repair_context["final_file_ops"]] == ["src/app.py"]
    assert repair_steps == ["analyze", "plan", "fix", "respond"]
    test_step = next(step for step in repair_context["meta"]["deferred_steps"] if step == "test")
    assert test_step == "test"

    _, review_context, review_steps = execute("请审查 src/app.py 代码有没有风险")
    assert review_context["meta"]["intent"] == "code_review"
    assert review_context["meta"]["collaboration_mode"] == "reviewer"
    assert review_context["final_file_ops"] == []
    assert review_steps == ["analyze", "plan", "respond"]


def test_workspace_step_streams_progress_and_reports_real_command_results(monkeypatch):
    progress_messages = []
    setup_calls = []
    monkeypatch.setattr(
        workspace_step,
        "stream_start",
        lambda *_args, **_kwargs: progress_messages.append("start"),
    )
    monkeypatch.setattr(
        workspace_step,
        "stream_chunk",
        lambda _task_id, content, **kwargs: progress_messages.append(
            (content, kwargs.get("channel"))
        ),
    )
    monkeypatch.setattr(
        workspace_step,
        "stream_end",
        lambda *_args, **_kwargs: progress_messages.append("end"),
    )

    def fake_setup(**kwargs):
        setup_calls.append(kwargs)
        kwargs["progress"]("创建虚拟环境 .vnev")
        return [
            {
                "name": "create_venv",
                "status": "completed",
                "command": ["python", "-m", "venv", ".vnev"],
                "exit_code": 0,
                "stdout": "environment ready",
                "stderr": "",
            },
            {
                "name": "install_inferred_dependencies",
                "status": "completed",
                "exit_code": 0,
                "stdout": "Successfully installed pandas-3.0.6 scikit-learn-1.9.1",
                "stderr": "",
                "installed_packages": ["pandas", "scikit-learn"],
            },
        ]

    monkeypatch.setattr(workspace_step, "setup_python_environment", fake_setup)
    context = {
        "meta": {
            "workspace_scan": {
                "root": "C:/workspace",
                "python_file_count": 4,
                "fixable_issue_count": 0,
                "issues": [],
                "scan_errors": [],
                "inferred_dependencies": ["pandas", "scikit-learn"],
                "unresolved_imports": ["internal_plugin"],
            },
            "user_request": "创建虚拟环境 .vnev 并安装依赖",
            "workspace_path": "C:/workspace",
        },
        "final_file_ops": [],
    }
    step = {}
    events = []

    workspace_step.run_workspace_step(step, context, events, task_id="workspace-progress")

    streamed_chunks = [
        message for message in progress_messages if isinstance(message, tuple)
    ]
    assert setup_calls[0]["venv_name"] == ".vnev"
    assert setup_calls[0]["inferred_dependencies"] == ["pandas", "scikit-learn"]
    assert any(
        "正在创建 Python 虚拟环境" in message for message, _ in streamed_chunks
    )
    assert all(channel == "tool" for _, channel in streamed_chunks)
    assert "已安装 2 个依赖包。" in step["output"]["text"]
    assert "工具运行日志" not in step["output"]["text"]
    assert "python -m venv" not in step["output"]["text"]
    assert "environment ready" not in step["output"]["text"]
    assert context["tool_outputs"][0]["installed_package_count"] == 2
    assert context["tool_outputs"][0]["operations"][0]["exit_code"] == 0
    assert any(event.get("type") == "tool_completed" for event in events)


def test_installed_package_count_uses_only_successfully_installed_unique_packages():
    from python_worker.workspace_tools import _command_operation

    operation = _command_operation(
        "install_dependencies",
        ["python", "-m", "pip", "install"],
        {
            "exit_code": 0,
            "stdout": "Successfully installed PyJWT-2.15.1 sqlalchemy-2.1.3 pydantic-2.13.5",
            "stderr": "",
        },
    )

    assert operation["installed_packages"] == ["pydantic", "PyJWT", "sqlalchemy"]
