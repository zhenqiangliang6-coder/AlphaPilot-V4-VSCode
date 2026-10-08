# -*- coding: utf-8 -*-
# test_intent_router.py
# ---------------------------------------------------------
# Intent Router 单元测试 (v2.6)
# 验证意图识别的准确性和鲁棒性
# ---------------------------------------------------------

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from intent_router import IntentRouter, requires_authorization_before_step
from collaboration_modes import prepare_collaboration_mode


def test_write_code_detection():
    """测试代码生成意图识别"""
    test_cases = [
        ("写一个排序算法", "write_code", "engineer"),
        ("实现快速排序", "write_code", "engineer"),
        ("创建一个函数来计算斐波那契数列", "write_code", "engineer"),
        ("在现有项目基础上，新增数据可视化模块", "write_code", "engineer"),
        ("在 src/data_loader.py 增加 JSONL 加载支持，并更新测试", "write_code", "engineer"),
        ("write a sorting algorithm", "write_code", "engineer"),
        ("Add JSONL support to the existing data loader", "write_code", "engineer"),
        ("implement binary search", "write_code", "engineer"),
    ]
    
    print("\n🧪 测试代码生成意图识别")
    for prompt, expected_intent, expected_persona in test_cases:
        intent, persona, chain = IntentRouter.detect_intent(prompt)
        assert intent == expected_intent, f"预期 {expected_intent}, 实际 {intent}"
        assert persona == expected_persona, f"预期 {expected_persona}, 实际 {persona}"
        print(f"  ✅ '{prompt[:30]}...' → {intent} ({persona})")


def test_full_stack_multi_client_design_requests_route_to_engineer_with_approval():
    prompts = [
        "请用架构师的身份帮我设计一个村民选举投票系统，有后端前端，以后可以网页，App，小程序后端不改都能接入",
        "Design a village election voting system with a backend and frontend that web, mobile apps, and mini-programs can use without backend changes.",
        "请按全栈项目交付，搭建支持网页和手机 App 的前后端系统",
        "Build a full-stack project with a frontend and backend for web and mobile clients.",
    ]

    for prompt in prompts:
        intent, persona, _ = IntentRouter.detect_intent(prompt)
        plan = IntentRouter.plan_request(prompt)
        collaboration_mode, _, _ = prepare_collaboration_mode(
            None, prompt, plan["execution_chain"], intent=intent
        )

        assert (intent, persona) == ("write_code", "engineer")
        assert collaboration_mode == "engineer"
        assert plan["mode"] == "ENGINEER_EXECUTE"
        assert plan["approval"]["required"] is True
        assert "workspace file changes" in plan["approval"]["before"]
        assert "write" in plan["execution_chain"]


def test_architecture_only_requests_remain_read_only():
    prompts = [
        "请从架构师角度设计投票系统模块和接口，只提供设计方案，不生成代码。",
        "Design the architecture only; do not implement it or create source files.",
    ]

    for prompt in prompts:
        intent, persona, _ = IntentRouter.detect_intent(prompt)

        assert (intent, persona) == ("architecture", "architect")


def test_explain_code_detection():
    """测试代码解释意图识别"""
    test_cases = [
        ("解释一下这段代码", "explain_code", "engineer"),
        ("这是什么意思", "explain_code", "engineer"),
        ("帮我看看这个函数", "explain_code", "engineer"),  # ⭐ 修改: 避免与 analysis 冲突
        ("explain this code", "explain_code", "engineer"),
        ("what does this function do", "explain_code", "engineer"),
    ]
    
    print("\n🧪 测试代码解释意图识别")
    for prompt, expected_intent, expected_persona in test_cases:
        intent, persona, chain = IntentRouter.detect_intent(prompt)
        assert intent == expected_intent, f"预期 {expected_intent}, 实际 {intent}"
        assert persona == expected_persona, f"预期 {expected_persona}, 实际 {persona}"
        print(f"  ✅ '{prompt[:30]}...' → {intent} ({persona})")


def test_fix_code_detection():
    """测试错误修复意图识别"""
    test_cases = [
        ("修复这个bug", "fix_code", "engineer"),
        ("这段代码报错了", "fix_code", "engineer"),
        ("为什么运行不了", "fix_code", "engineer"),
        ("fix this error", "fix_code", "engineer"),
        ("debug the code", "fix_code", "engineer"),
    ]
    
    print("\n🧪 测试错误修复意图识别")
    for prompt, expected_intent, expected_persona in test_cases:
        intent, persona, chain = IntentRouter.detect_intent(prompt)
        assert intent == expected_intent, f"预期 {expected_intent}, 实际 {intent}"
        assert persona == expected_persona, f"预期 {expected_persona}, 实际 {persona}"
        print(f"  ✅ '{prompt[:30]}...' → {intent} ({persona})")


def test_creative_writing_detection():
    """测试创意写作意图识别"""
    test_cases = [
        ("写一首关于春天的诗", "creative_writing", "creator"),
        ("创作一个故事", "creative_writing", "creator"),
        ("写一篇散文", "creative_writing", "creator"),
        ("write a poem about love", "creative_writing", "creator"),
        ("create a short story", "creative_writing", "creator"),
    ]
    
    print("\n🧪 测试创意写作意图识别")
    for prompt, expected_intent, expected_persona in test_cases:
        intent, persona, chain = IntentRouter.detect_intent(prompt)
        assert intent == expected_intent, f"预期 {expected_intent}, 实际 {intent}"
        assert persona == expected_persona, f"预期 {expected_persona}, 实际 {persona}"
        print(f"  ✅ '{prompt[:30]}...' → {intent} ({persona})")


def test_chat_detection():
    """测试闲聊意图识别"""
    test_cases = [
        ("你觉得人工智能未来会怎样", "chat", "conversational"),
        ("你怎么看这个问题", "chat", "conversational"),
        ("聊聊你的想法", "chat", "conversational"),
        ("what do you think about AI", "chat", "conversational"),
        ("how are you today", "chat", "conversational"),
    ]
    
    print("\n🧪 测试闲聊意图识别")
    for prompt, expected_intent, expected_persona in test_cases:
        intent, persona, chain = IntentRouter.detect_intent(prompt)
        assert intent == expected_intent, f"预期 {expected_intent}, 实际 {intent}"
        assert persona == expected_persona, f"预期 {expected_persona}, 实际 {persona}"
        print(f"  ✅ '{prompt[:30]}...' → {intent} ({persona})")


def test_default_fallback():
    """Unknown and empty requests use a non-mutating conversation route."""
    test_cases = [
        ("这是一个普通的句子", "chat", "conversational"),
        ("", "chat", "conversational"),
    ]
    
    print("\n🧪 测试默认降级逻辑")
    for prompt, expected_intent, expected_persona in test_cases:
        intent, persona, chain = IntentRouter.detect_intent(prompt)
        assert intent == expected_intent, f"预期 {expected_intent}, 实际 {intent}"
        assert persona == expected_persona, f"预期 {expected_persona}, 实际 {persona}"
        print(f"  ✅ '{prompt[:30]}...' → {intent} ({persona}) [default]")


def test_execution_chain_mapping():
    """测试执行链路映射"""
    test_cases = [
        ("写代码", ["analyze", "plan", "write", "refine", "test"]),
        ("解释代码", ["analyze", "plan", "respond"]),
        ("修复bug", ["analyze", "fix", "test"]),
        ("写诗", ["analyze", "plan", "write", "refine"]),
        ("聊天", ["analyze", "plan", "respond"]),
        ("创作故事", ["analyze", "plan", "write", "refine"]),
    ]
    
    print("\n🧪 测试执行链路映射")
    for prompt, expected_chain in test_cases:
        intent, persona, chain = IntentRouter.detect_intent(prompt)
        assert chain == expected_chain, f"预期 {expected_chain}, 实际 {chain}"
        print(f"  ✅ '{prompt}' → {' → '.join(chain)}")


def test_v35_intent_plans_fail_closed_for_unavailable_capabilities():
    mentor = IntentRouter.plan_request("这个项目怎么人工测试？")
    assert mentor["mode"] == "MENTOR_EXPLAIN"
    assert mentor["persona"] == "mentor"
    assert "write" not in mentor["execution_chain"]
    assert mentor["side_effects"] == []
    assert {item["id"] for item in mentor["capabilities"] if not item["available"]} == {"workspace.read"}

    engineer = IntentRouter.plan_request("帮我把项目中 Python 文件的缩进统一一下")
    assert engineer["mode"] == "ENGINEER_EXECUTE"
    assert engineer["approval"]["required"] is True
    assert "workspace file changes" in engineer["approval"]["before"]

    git_plan = IntentRouter.plan_request("帮我上传 GitHub")
    assert git_plan["mode"] == "EXTERNAL_CAPABILITY"
    assert git_plan["approval"]["required"] is True
    assert all(not item["available"] for item in git_plan["capabilities"])
    assert "git.push" not in git_plan["execution_chain"]


def test_workspace_maintenance_requests_route_to_real_workspace_tools():
    prompt = "读取项目文件检查项目里的代码文件语法和缩进错误并修改，创建虚拟环境.vnev并安装项目所需的第三方相关库"
    intent, persona, chain = IntentRouter.detect_intent(prompt)
    plan = IntentRouter.plan_request(prompt, workspace_available=True)

    assert (intent, persona) == ("workspace_maintenance", "engineer")
    assert chain == ["analyze", "fix", "workspace"]
    assert plan["mode"] == "WORKSPACE_MAINTENANCE"
    assert all(capability["available"] for capability in plan["capabilities"])
    assert plan["approval"]["required"] is False


def test_real_chinese_requests_choose_intent_and_chain():
    scenarios = [
        (
            "帮我修改项目代码的缩进错误",
            "workspace_maintenance",
            "engineer",
            ["analyze", "fix", "workspace"],
        ),
        (
            "帮我定一首关于秋天的诗",
            "creative_writing",
            "creator",
            ["analyze", "plan", "write", "refine"],
        ),
        (
            "教我如何使用这个项目",
            "mentor_explain",
            "mentor",
            ["analyze", "plan", "respond"],
        ),
        (
            "你帮我看看这个错误是什么，并帮我解决",
            "explain_and_fix",
            "engineer",
            ["analyze", "plan", "fix", "test", "respond"],
        ),
        (
            "请审查这个项目代码有没有风险",
            "code_review",
            "reviewer",
            ["analyze", "plan", "respond"],
        ),
        (
            "帮我检查 src/ 和 tests/目录下所有文件的代码质量",
            "code_review",
            "reviewer",
            ["analyze", "plan", "respond"],
        ),
        (
            "请作为架构师设计系统架构",
            "architecture",
            "architect",
            ["analyze", "plan", "write"],
        ),
        (
            "请删除 src/obsolete.py",
            "delete_files",
            "file_manager",
            ["analyze", "plan", "write"],
        ),
        (
            "请设计系统架构并将架构文档写入 docs/architecture.md，不要实现应用源代码",
            "architecture",
            "architect",
            ["analyze", "plan", "write"],
        ),
    ]

    for prompt, expected_intent, expected_persona, expected_chain in scenarios:
        intent, persona, chain = IntentRouter.detect_intent(prompt)
        assert (intent, persona, chain) == (expected_intent, expected_persona, expected_chain)


def test_followup_request_to_execute_previous_design_routes_to_engineer():
    prompt = "好的按照上面的对话执行项目编写"

    intent, persona, chain = IntentRouter.detect_intent(prompt)
    plan = IntentRouter.plan_request(prompt)
    mode, _, mode_chain = prepare_collaboration_mode(
        "automatic",
        prompt,
        plan["execution_chain"],
        intent=intent,
    )

    assert (intent, persona) == ("write_code", "engineer")
    assert chain == ["analyze", "plan", "write", "refine", "test"]
    assert plan["mode"] == "ENGINEER_EXECUTE"
    assert plan["approval"]["required"] is True
    assert mode == "engineer"
    assert mode_chain == chain


def test_execution_chains_have_one_source_and_adapt_to_worker_capabilities():
    prompt = "请写代码并生成 README 文档"
    assert IntentRouter.execution_chain_for("write_code", prompt=prompt) == [
        "analyze", "plan", "write", "refine", "test", "doc"
    ]
    assert IntentRouter.execution_chain_for("code_review", worker="standard") == [
        "analyze", "plan", "write"
    ]
    assert IntentRouter.execution_chain_for("workspace_maintenance", worker="standard") == [
        "analyze", "plan"
    ]


def test_explain_review_and_chat_plans_are_read_only():
    for prompt in (
        "教我如何使用这个项目",
        "解释一下这段代码",
        "请审查这个项目代码有没有风险",
        "这是一个普通的问题",
    ):
        plan = IntentRouter.plan_request(prompt, workspace_available=True)
        assert plan["approval"]["required"] is False
        assert plan["side_effects"] == []

    review = IntentRouter.plan_request("请审查这个项目代码有没有风险")
    assert review["mode"] == "REVIEW_ONLY"
    assert review["persona"] == "reviewer"


def test_read_only_chat_uses_response_chain_and_code_tests_require_authorization():
    chat = IntentRouter.plan_request("你好")
    fix = IntentRouter.plan_request("修复这个错误")

    assert chat["execution_chain"] == ["analyze", "plan", "respond"]
    assert not requires_authorization_before_step(chat, "test")
    assert requires_authorization_before_step(fix, "test")


if __name__ == "__main__":
    print("=" * 60)
    print("  Intent Router 单元测试 (v2.6)")
    print("=" * 60)
    
    try:
        test_write_code_detection()
        test_explain_code_detection()
        test_fix_code_detection()
        test_creative_writing_detection()
        test_chat_detection()
        test_default_fallback()
        test_execution_chain_mapping()
        test_v35_intent_plans_fail_closed_for_unavailable_capabilities()
        test_workspace_maintenance_requests_route_to_real_workspace_tools()
        
        print("\n" + "=" * 60)
        print("  ✅ 所有测试通过!")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
