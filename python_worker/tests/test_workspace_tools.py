import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import workspace_tools


def test_detects_requested_vnev_and_dependency_install():
    request = "检查项目语法，创建虚拟环境.vnev并安装项目所需的第三方相关库"

    actions = workspace_tools.detect_environment_requests(request)

    assert actions == {
        "create_venv": True,
        "install_dependencies": True,
        "venv_name": ".vnev",
    }


def test_creates_requested_venv_and_installs_declared_requirements(tmp_path, monkeypatch):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("sample-dependency\n", encoding="utf-8")
    executed_commands = []

    def fake_run(command, cwd, timeout):
        executed_commands.append(command)
        if command[1:3] == ["-m", "venv"]:
            executable = tmp_path / ".vnev" / "Scripts" / "python.exe"
            executable.parent.mkdir(parents=True)
            executable.write_text("", encoding="utf-8")
        return {"exit_code": 0, "stdout": "installed", "stderr": ""}

    monkeypatch.setattr(workspace_tools, "_run", fake_run)
    progress = []
    operations = workspace_tools.setup_python_environment(
        str(tmp_path),
        ".vnev",
        create_venv=True,
        install_dependencies=True,
        progress=progress.append,
    )

    assert [operation["status"] for operation in operations] == ["completed", "completed"]
    assert executed_commands[0][1:3] == ["-m", "venv"]
    assert executed_commands[1][-2:] == ["-r", str(requirements)]
    assert operations[1]["manifest"] == "requirements.txt"
    assert any("创建虚拟环境 .vnev" in message for message in progress)


def test_creates_a_real_project_venv_without_running_package_installers(tmp_path):
    operations = workspace_tools.setup_python_environment(
        str(tmp_path),
        ".vnev",
        create_venv=True,
        install_dependencies=False,
        progress=lambda _message: None,
    )

    interpreter = workspace_tools._venv_python(tmp_path / ".vnev")
    assert operations[0]["status"] == "completed"
    assert interpreter.is_file()


def test_installs_dependencies_inferred_from_source_without_manifest(tmp_path, monkeypatch):
    environment_python = tmp_path / ".venv" / "Scripts" / "python.exe"
    environment_python.parent.mkdir(parents=True)
    environment_python.write_text("", encoding="utf-8")
    calls = []
    monkeypatch.setattr(
        workspace_tools,
        "_run",
        lambda *args, **kwargs: calls.append(args) or {
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
        },
    )

    operations = workspace_tools.setup_python_environment(
        str(tmp_path),
        ".venv",
        create_venv=False,
        install_dependencies=True,
        progress=lambda _message: None,
        inferred_dependencies=["pandas", "scikit-learn", "joblib"],
    )

    assert operations[0]["name"] == "install_inferred_dependencies"
    assert operations[0]["status"] == "completed"
    assert calls[0][0][1:6] == [
        "-m",
        "pip",
        "--disable-pip-version-check",
        "--no-input",
        "install",
    ]
    assert calls[0][0][-3:] == ["joblib", "pandas", "scikit-learn"]


def test_does_not_guess_dependencies_when_scan_found_no_safe_import_mapping(tmp_path, monkeypatch):
    environment_python = tmp_path / ".venv" / "Scripts" / "python.exe"
    environment_python.parent.mkdir(parents=True)
    environment_python.write_text("", encoding="utf-8")
    calls = []
    monkeypatch.setattr(
        workspace_tools,
        "_run",
        lambda *args, **kwargs: calls.append(args) or {
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
        },
    )

    operations = workspace_tools.setup_python_environment(
        str(tmp_path),
        ".venv",
        create_venv=False,
        install_dependencies=True,
        progress=lambda _message: None,
        inferred_dependencies=[],
    )

    assert operations[0]["status"] == "skipped"
    assert "未识别到" in operations[0]["output"]
    assert calls == []
