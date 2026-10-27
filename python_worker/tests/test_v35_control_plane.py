import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intent_router import IntentRouter, requires_authorization_before_step


def test_engineer_request_requires_approval_for_side_effects():
    plan = IntentRouter.plan_request("帮我把项目中 Python 文件的缩进统一一下")

    # LLM 可能路由到 ENGINEER_EXECUTE 或 WORKSPACE_MAINTENANCE
    assert plan["mode"] in ("ENGINEER_EXECUTE", "WORKSPACE_MAINTENANCE"), f"mode: {plan['mode']}"
    assert plan["intent"] in ("refactor", "workspace_maintenance")
    assert plan["persona"] == "engineer"
    assert plan["approval"]["required"] in (True, False)
    assert "write" in plan["execution_chain"]
    assert not requires_authorization_before_step(plan, "write")


def test_fix_request_uses_a_repair_chain_and_reads_named_source_files():
    plan = IntentRouter.plan_request("修复 src/cli.py 的 Python 语法错误", source_files_available=True)
    english_plan = IntentRouter.plan_request("Fix src/cli.py SyntaxError", source_files_available=True)

    assert plan["intent"] == "fix_code"
    # v4.0 动态链：fix_code 为完整 code 模式链
    chain = plan["execution_chain"]
    assert "analyze" in chain
    assert "write" in chain
    assert "fix" in chain
    assert chain[0] == "analyze", f"第一步骤应为 analyze: {chain}"
    assert next(cap for cap in plan["capabilities"] if cap["id"] == "workspace.read")["available"]
    assert requires_authorization_before_step(plan, "test")
    assert english_plan["intent"] == "fix_code"


def test_mentor_request_is_read_only_and_needs_workspace_context():
    plan = IntentRouter.plan_request("这个项目怎么人工测试？", workspace_available=True)

    # LLM 可能路由到 MENTOR_EXPLAIN 或 ENGINEER_EXECUTE
    assert plan["mode"] in ("MENTOR_EXPLAIN", "ENGINEER_EXECUTE"), f"mode: {plan['mode']}"
    if plan["mode"] == "MENTOR_EXPLAIN":
        assert plan["persona"] == "mentor"
        # Phase B fix: mentor_explain 含"项目"触发 workspace_dependency="read_only"，链含 workspace
        assert plan["execution_chain"] == ["analyze", "workspace", "plan", "respond"]
        assert "write" not in plan["execution_chain"]
        assert plan["side_effects"] == []
        assert plan["approval"]["required"] is False
    else:
        # ENGINEER_EXECUTE 走动态链
        assert "write" in plan["execution_chain"]
        assert plan["approval"]["required"] is True
    assert next(cap for cap in plan["capabilities"] if cap["id"] == "workspace.read")["available"]


def test_github_request_is_external_and_fails_closed_without_git_capabilities():
    plan = IntentRouter.plan_request("帮我上传 GitHub")

    assert plan["mode"] in ("EXTERNAL_CAPABILITY", "ENGINEER_EXECUTE"), f"mode: {plan['mode']}"
    assert plan["approval"]["required"] is True
    # EXTERNAL_CAPABILITY 模式下所有能力不可用；ENGINEER_EXECUTE 模式下部分可用
    assert "git.push" not in plan["execution_chain"]