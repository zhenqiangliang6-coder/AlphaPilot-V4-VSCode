import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intent_router import IntentRouter, requires_authorization_before_step


def test_engineer_request_requires_approval_for_side_effects():
    plan = IntentRouter.plan_request("帮我把项目中 Python 文件的缩进统一一下")

    assert plan["mode"] == "ENGINEER_EXECUTE"
    assert plan["intent"] == "refactor"
    assert plan["persona"] == "engineer"
    assert plan["approval"]["required"] is True
    assert "workspace file changes" in plan["approval"]["before"]
    assert requires_authorization_before_step(plan, "test")
    assert not requires_authorization_before_step(plan, "fix")
    assert not requires_authorization_before_step(plan, "write")


def test_fix_request_uses_a_repair_chain_and_reads_named_source_files():
    plan = IntentRouter.plan_request("修复 src/cli.py 的 Python 语法错误", source_files_available=True)
    english_plan = IntentRouter.plan_request("Fix src/cli.py SyntaxError", source_files_available=True)

    assert plan["intent"] == "fix_code"
    assert plan["execution_chain"] == ["analyze", "fix", "test"]
    assert next(cap for cap in plan["capabilities"] if cap["id"] == "workspace.read")["available"]
    assert requires_authorization_before_step(plan, "test")
    assert english_plan["intent"] == "fix_code"


def test_mentor_request_is_read_only_and_needs_workspace_context():
    plan = IntentRouter.plan_request("这个项目怎么人工测试？", workspace_available=True)

    assert plan["mode"] == "MENTOR_EXPLAIN"
    assert plan["persona"] == "mentor"
    assert plan["execution_chain"] == ["analyze", "plan", "respond"]
    assert "write" not in plan["execution_chain"]
    assert plan["side_effects"] == []
    assert plan["approval"]["required"] is False
    assert next(cap for cap in plan["capabilities"] if cap["id"] == "workspace.read")["available"]


def test_github_request_is_external_and_fails_closed_without_git_capabilities():
    plan = IntentRouter.plan_request("帮我上传 GitHub")

    assert plan["mode"] == "EXTERNAL_CAPABILITY"
    assert plan["approval"]["required"] is True
    assert all(not capability["available"] for capability in plan["capabilities"])
    assert "git.push" not in plan["execution_chain"]
    assert requires_authorization_before_step(plan, "test")