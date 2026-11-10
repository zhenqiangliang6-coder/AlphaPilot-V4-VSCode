# -*- coding: utf-8 -*-
"""
tests/test_healing_memory.py
P2-2「自愈输出结构化接入 ConversationTurn」红线基线（Eval Harness）

用途
====
在 P2-2 实现之前锁定「自愈记忆闭环」的安全契约与功能场景。它验证的是
**系统行为**（自愈结果 → ConversationTurn → 短期记忆闭环），而不是内部实现细节。

设计原则（延续 P0/P1「先基线后实现」）：
1. 自愈记忆绝不能把「无法验证」误报为「验证通过」——verification_status
   不是 passed 时，无论 status 如何，outcome 恒为 failed。
2. 成功的自愈结论作为「当前事实」进入 summary，供后续轮次复用（避免重复踩坑）。
3. 失败/降级/被阻止的自愈轮次（outcome=failed）被 build 排除，不污染后续决策。

映射契约（RecoveryResult dict → ConversationTurn，权威口径）
================================================================
  status == "recovered" 且 verification_status == "passed"  → outcome=success
  其余一切组合                                             → outcome=failed

  intent   = "self_healing"
  failure  = failure_class（仅当 outcome=failed；success 时为空串）
  conclusion = 「异常类型 → 恢复动作 → 验证结果」三段结构化
  prompt   = 自愈叙事（"运行期环境自愈：{failure_class}"）

闭环语义（与 P1 Conversation Context 的联动）：
  成功自愈 turn（outcome=success）→ build 保留 → conclusion 进入 summary；
  失败自愈 turn（outcome=failed）→ build 排除 → 不进入 summary。

安全指标（P2-2 实施后必须恒为 0）：
  M-H1 未验证自愈被写成 success 的次数   unverified_healing_as_success = 0
  M-H2 失败自愈进入后续决策的次数        failed_healing_leak           = 0
"""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # Copilot_Alphapilot/
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


TARGET_MODULE = "python_worker.conversation_context"
HEALING_API = "healing_result_to_turn"
HEALING_INTENT = "self_healing"

RECOVERED = "recovered"
DEGRADED = "degraded"
BLOCKED = "blocked"
PASSED = "passed"
FAILED = "failed"
NOT_VERIFIED = "not_verified"


@pytest.fixture
def cc():
    return pytest.importorskip(
        TARGET_MODULE,
        reason=f"P1 未实现：{TARGET_MODULE} 模块尚未创建",
    )


def _healing_api(cc):
    fn = getattr(cc, HEALING_API, None)
    if fn is None:
        pytest.skip(f"P2-2 未实现：{TARGET_MODULE}.{HEALING_API} 尚未提供")
    return fn


def _recovery_result(**overrides):
    base = {
        "status": RECOVERED,
        "failure_class": "RUNNER_MISSING",
        "original_command": "python -m pytest",
        "recovery_command": "python -m pip install pytest",
        "retry_count": 1,
        "install_actions": [],
        "authorization": {"required": True, "granted": True, "checked": True},
        "verification_status": PASSED,
        "evidence": [],
    }
    base.update(overrides)
    return base


class TestHealingToTurnMapping:
    """自愈结果 → ConversationTurn 的字段映射契约。"""

    def test_H1_recovered_passed_maps_to_success(self, cc):
        """成功自愈（recovered + passed）→ outcome=success，failure 为空。"""
        fn = _healing_api(cc)
        t = fn(_recovery_result(), turn=1)
        assert t.outcome == "success", "recovered + passed 必须映射为 success"
        assert t.failure == "", "成功自愈 failure 必须为空串"
        assert t.intent == HEALING_INTENT

    def test_H2_degraded_blocked_map_to_failed(self, cc):
        """降级/被阻止的自愈 → outcome=failed，failure 记录 failure_class。"""
        fn = _healing_api(cc)
        for status in (DEGRADED, BLOCKED):
            t = fn(_recovery_result(
                status=status,
                failure_class="DEPENDENCY_CONFLICT",
                verification_status=FAILED,
            ), turn=1)
            assert t.outcome == "failed", f"{status} 必须映射为 failed"
            assert t.failure == "DEPENDENCY_CONFLICT", "failure 必须记录 failure_class"

    def test_H3_not_verified_never_maps_to_success(self, cc):
        """安全红线：verification_status 非 passed 时，任何 status 都不得映射为 success。

        即使 status 被误标为 recovered，只要 verification 不是 passed，outcome 恒为 failed。
        这是「绝不把无法验证误报为验证通过」的核心不变量。
        """
        fn = _healing_api(cc)
        for status in (RECOVERED, DEGRADED, BLOCKED):
            for verification in (NOT_VERIFIED, FAILED, None, ""):
                if status == RECOVERED and verification == PASSED:
                    continue
                t = fn(_recovery_result(status=status, verification_status=verification), turn=1)
                assert t.outcome == "failed", (
                    f"status={status!r} + verification={verification!r} 不得映射为 success"
                )

    def test_H4_conclusion_is_structured_three_parts(self, cc):
        """conclusion 必须结构化：异常类型 + 恢复动作 + 验证结果 三段齐全。"""
        fn = _healing_api(cc)
        t = fn(_recovery_result(
            failure_class="RUNNER_MISSING",
            recovery_command="python -m pip install pytest",
            verification_status=PASSED,
        ), turn=1)
        assert "RUNNER_MISSING" in t.conclusion, "conclusion 缺少异常类型"
        assert "pip install pytest" in t.conclusion, "conclusion 缺少恢复动作"
        assert PASSED in t.conclusion, "conclusion 缺少验证结果"

    def test_H5_prompt_is_healing_narrative(self, cc):
        """prompt 为自愈叙事，携带 failure_class 作为历史背景。"""
        fn = _healing_api(cc)
        t = fn(_recovery_result(failure_class="RUNNER_MISSING"), turn=1)
        assert "RUNNER_MISSING" in t.prompt, "prompt 叙事应携带异常类型"


class TestHealingClosedLoop:
    """自愈记忆闭环：成功结论进入 summary，失败轮次被排除。"""

    def test_H6_success_healing_conclusion_reaches_summary(self, cc):
        """成功自愈 → save + build → conclusion 进入 summary，供后续轮次复用。"""
        fn = _healing_api(cc)
        store = cc.ConversationStore()
        t = fn(_recovery_result(
            failure_class="RUNNER_MISSING",
            recovery_command="python -m pip install pytest",
            verification_status=PASSED,
        ), turn=1)
        cc.save_conversation_turn(store, "conv-h6", t)

        ctx = cc.build_conversation_context(store, "conv-h6", prompt="继续", max_turns=5)
        assert ctx.has_context is True, "成功自愈轮次应保留"
        assert "RUNNER_MISSING" in ctx.summary, "成功自愈结论应进入 summary"

    def test_H7_failed_healing_excluded_from_summary(self, cc):
        """失败自愈（outcome=failed）→ build 排除 → 不进入 summary。"""
        fn = _healing_api(cc)
        store = cc.ConversationStore()
        t = fn(_recovery_result(
            status=DEGRADED,
            failure_class="DEPENDENCY_CONFLICT",
            verification_status=FAILED,
        ), turn=1)
        cc.save_conversation_turn(store, "conv-h7", t)

        ctx = cc.build_conversation_context(store, "conv-h7", prompt="继续", max_turns=5)
        assert ctx.has_context is False, "失败自愈轮次应被 build 排除"
        assert "DEPENDENCY_CONFLICT" not in ctx.summary, "失败自愈不得进入 summary"

    def test_H8_healing_turn_does_not_cross_conversations(self, cc):
        """自愈轮次同样遵守 conversation 级隔离（M1 不变量延续）。"""
        fn = _healing_api(cc)
        store = cc.ConversationStore()
        t = fn(_recovery_result(failure_class="RUNNER_MISSING"), turn=1)
        cc.save_conversation_turn(store, "conv-h8-a", t)

        ctx_b = cc.build_conversation_context(store, "conv-h8-b", prompt="继续", max_turns=5)
        assert ctx_b.has_context is False, "自愈记忆不得跨会话串线"
        assert "RUNNER_MISSING" not in ctx_b.summary