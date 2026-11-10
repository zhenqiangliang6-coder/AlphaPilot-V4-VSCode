from types import SimpleNamespace
from unittest.mock import patch

import pytest

from python_worker.intent_router import IntentRouter
from python_worker.agents.qwen import compound_executor
from python_worker.agents.qwen.task_context import scan_workspace_for_intent
from python_worker.context_builder import discover_project_test_command, read_project_context


@pytest.fixture(autouse=True)
def disable_llm_intent_classification(monkeypatch):
    def classify(cls, prompt, model_name="qwen"):
        cls._last_classify_result = None
        return None

    monkeypatch.setattr(IntentRouter, "_llm_classify", classmethod(classify))


def test_project_test_request_uses_existing_test_workflow_without_code_generation():
    prompt = "帮我运行这个项目的测试，失败时修复并重新验证"

    intent, persona, chain = IntentRouter.detect_intent(prompt)
    plan = IntentRouter.plan_request(prompt)
    compound = IntentRouter.detect_intent_multi(prompt)

    assert intent == "run_tests"
    assert persona == "engineer"
    assert chain == ["analyze", "plan", "test"]
    assert plan["intent"] == "run_tests"
    assert plan["mode"] == "TEST_EXECUTION"
    assert plan["approval"]["required"] is True
    assert plan["execution_chain"] == chain
    assert compound.is_compound is False
    assert IntentRouter.requests_test_failure_repair(prompt) is True


def test_test_only_request_does_not_opt_into_automatic_repair_without_request():
    prompt = "运行这个项目的测试并告诉我结果"

    assert IntentRouter.detect_intent(prompt)[0] == "run_tests"
    assert IntentRouter.requests_test_failure_repair(prompt) is False


def test_read_only_test_context_includes_package_test_configuration(tmp_path):
    package_manifest = tmp_path / "package.json"
    package_manifest.write_text(
        '{"scripts":{"test":"vitest run"}}',
        encoding="utf-8",
    )
    (tmp_path / "vitest.config.ts").write_text(
        "export default {}",
        encoding="utf-8",
    )

    project_context, context_files = read_project_context(str(tmp_path))

    assert "package.json" in context_files
    assert "vitest.config.ts" in context_files
    assert '"test":"vitest run"' in project_context


def test_test_command_discovery_uses_existing_python_tests_when_manifest_is_invalid(tmp_path):
    (tmp_path / "package.json").write_text("not valid json", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_api.py").write_text("def test_api(): pass", encoding="utf-8")

    assert discover_project_test_command(str(tmp_path)) == "python -m pytest"


def test_test_command_discovery_uses_npm_only_for_a_valid_test_script(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"jest"}}',
        encoding="utf-8",
    )

    assert discover_project_test_command(str(tmp_path)) == "npm test"


def test_test_command_discovery_does_not_guess_when_project_has_no_test_config(tmp_path):
    (tmp_path / "README.md").write_text("A project without test setup.", encoding="utf-8")

    assert discover_project_test_command(str(tmp_path)) is None


def test_test_workspace_scan_carries_the_discovered_command_to_worker_context(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_api.py").write_text("def test_api(): pass", encoding="utf-8")

    scan = scan_workspace_for_intent(
        "run_tests",
        {"workspace_path": str(tmp_path)},
        "",
        "运行项目测试",
        "运行项目测试",
    )

    assert scan["proposed_test_command"] == "python -m pytest"


def test_feature_implementation_with_tests_remains_a_code_change_request():
    prompt = "在项目里新增用户登录功能，然后运行测试"

    assert IntentRouter.detect_intent(prompt)[0] != "run_tests"


def test_repair_task_is_routed_to_code_changes_not_test_only():
    prompt = (
        "请实现必要的最小代码修改以修复以下测试错误。"
        "先读取并定位涉及的源文件，只修改与失败直接相关的内容。"
        "原始任务：运行项目测试并修复失败。"
        "测试命令会再次遵循先前授权的重试规则。"
    )

    assert IntentRouter.detect_intent(prompt)[0] == "write_code"


def test_compound_phases_stop_when_a_test_is_waiting_for_authorization():
    plan = SimpleNamespace(
        is_compound=True,
        phases=[
            SimpleNamespace(type="run_tests", prompt="运行项目测试"),
            SimpleNamespace(type="refactor", prompt="按结果修复"),
        ],
    )
    context = {"meta": {"execution_state": "awaiting_authorization"}}

    with patch.object(compound_executor, "_exec_code_phase") as execute_phase:
        compound_executor.exec_compound_phases(plan, {}, "", [], context)

    execute_phase.assert_not_called()
