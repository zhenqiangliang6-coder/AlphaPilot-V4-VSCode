import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collaboration_modes import (
    MODE_POLICIES,
    apply_mode_to_persona,
    enforce_file_operation_policy,
    infer_collaboration_mode,
    normalize_collaboration_mode,
    prepare_collaboration_mode,
)
from agents.qwen.personas import get_persona_config


def test_automatic_and_legacy_modes_are_supported_and_invalid_modes_default_to_automatic():
    assert set(MODE_POLICIES) == {
        "automatic", "architect", "teacher", "pair_programmer", "engineer",
        "reviewer", "file_manager", "creative", "navigator"
    }
    assert normalize_collaboration_mode("not-a-mode") == "automatic"


def test_automatic_mode_is_inferred_from_worker_intent():
    assert infer_collaboration_mode("mentor_explain") == "teacher"
    assert infer_collaboration_mode("architecture") == "architect"
    assert infer_collaboration_mode("delete_files") == "file_manager"
    assert infer_collaboration_mode("code_review") == "reviewer"
    assert infer_collaboration_mode("creative_writing") == "creative"
    assert infer_collaboration_mode("explain_and_fix") == "engineer"

    mode, _, chain = prepare_collaboration_mode(
        None, "写一首诗", ["analyze", "plan", "write", "refine"], intent="creative_writing"
    )
    assert mode == "creative"
    assert chain == ["analyze", "plan", "write", "refine"]


def test_read_only_modes_do_not_schedule_code_execution_steps():
    base_chain = ["analyze", "plan", "write", "test", "fix", "doc"]

    for mode in ("architect", "teacher", "reviewer", "creative", "navigator"):
        _, _, chain = prepare_collaboration_mode(mode, "request", base_chain)
        assert "test" not in chain
        assert "fix" not in chain


def test_creative_and_navigation_modes_use_short_chains():
    expected = ["analyze", "plan", "write"]
    assert prepare_collaboration_mode("creative", "poem", expected)[2] == expected
    assert prepare_collaboration_mode("navigator", "run app", expected)[2] == expected


def test_local_model_can_preserve_its_existing_limited_chain():
    _, _, chain = prepare_collaboration_mode(
        "teacher", "explain", ["write"], preserve_chain=True
    )
    assert chain == ["write"]


def test_persona_mode_injection_does_not_mutate_shared_persona_config():
    original = {"system_prompt": "base prompt"}
    updated = apply_mode_to_persona(original, "teacher")

    assert original["system_prompt"] == "base prompt"
    assert updated["system_prompt"].startswith("导师模式")


def test_read_only_modes_clear_all_file_operations():
    context = {
        "final_file_ops": [{"path": "generated.py"}],
        "file_ops": [{"path": "generated.py"}],
    }
    steps = [{"output": {"file_ops": [{"path": "generated.py"}]}}]
    events = [{"data": {"file_ops": [{"path": "generated.py"}]}}]

    enforce_file_operation_policy(context, "reviewer", steps=steps, events=events)

    assert context["final_file_ops"] == []
    assert context["file_ops"] == []
    assert steps[0]["output"]["file_ops"] == []
    assert events[0]["data"]["file_ops"] == []
    assert context["meta"]["collaboration_mode"] == "reviewer"
    assert context["meta"]["file_changes_allowed"] is False


def test_architect_only_writes_explicitly_requested_architecture_docs():
    context = {
        "meta": {
            "intent": "architecture",
            "user_request": "将架构文档写入 docs/architecture.md",
        },
        "final_file_ops": [
            {"op": "create", "path": "/docs/architecture.md"},
            {"op": "create", "path": "docs/architecture.mmd"},
            {"op": "create", "path": "docs/notes.md"},
            {"op": "modify", "path": "src/app.py"},
            {"op": "create", "path": "../docs/architecture.md"},
            {"op": "create", "path": "D:/project/docs/architecture.md"},
        ],
        "steps": [{
            "output": {
                "file_ops": [
                    {"op": "create", "path": "docs/architecture.md"},
                    {"op": "create", "path": "src/unrequested.py"},
                ]
            }
        }],
        "events": [{"data": {
            "final_file_ops": [
                {"op": "create", "path": "docs/architecture.md"},
                {"op": "create", "path": "docs/notes.md"},
            ]
        }}],
    }

    enforce_file_operation_policy(context, "architect")

    assert context["meta"]["file_changes_allowed"] is True
    assert [operation["path"] for operation in context["final_file_ops"]] == [
        "/docs/architecture.md",
        "docs/architecture.mmd",
    ]
    assert [operation["path"] for operation in context["steps"][0]["output"]["file_ops"]] == [
        "docs/architecture.md",
    ]
    assert [operation["path"] for operation in context["events"][0]["data"]["final_file_ops"]] == [
        "docs/architecture.md",
    ]


def test_architect_is_read_only_without_an_explicit_document_request():
    for prompt in (
        "请设计系统架构",
        "请设计架构，目标文件 docs/architecture.md，但不要写入",
        "不要生成架构文档",
    ):
        context = {
            "meta": {"intent": "architecture", "user_request": prompt},
            "final_file_ops": [{"op": "create", "path": "docs/architecture.md"}],
        }

        enforce_file_operation_policy(context, "architect")

        assert context["meta"]["file_changes_allowed"] is False
        assert context["final_file_ops"] == []


def test_architect_persona_is_registered():
    persona = get_persona_config("architect")

    assert persona["name"] == "架构师人格"
    assert "多文件协议 v3.0" in persona["system_prompt"]


def test_reviewer_persona_is_registered_and_read_only():
    persona = get_persona_config("reviewer")

    assert persona["name"] == "代码审查人格"
    assert "只读工作" in persona["system_prompt"]


def test_writable_modes_preserve_file_operations():
    file_ops = [{"path": "generated.py"}]
    context = {"final_file_ops": file_ops}

    enforce_file_operation_policy(context, "pair_programmer")

    assert context["final_file_ops"] == file_ops
    assert context["meta"]["file_changes_allowed"] is True