# -*- coding: utf-8 -*-
"""回归契约：文档-only 架构设计请求的意图分类确定性。

取证（2026-11-14 ShopFlow R5 真实跟测）：
  同一 Prompt、同一模型 qwen3.7-flash，连续 5 次 detect_intent：
    architecture / write_code / architecture / write_code / architecture
  → 40% 漂移。这不是测试环境抖动，是本体缺陷。

误判为 write_code 的连锁后果：
  - infer_collaboration_mode() 注入「工程师模式」，架构师只读文件策略守卫失效
  - R5 违规生成 8 个实现代码 .py 文件（题面明令禁止），旧验收却仍报四维全绿
  - 执行链多出 test / fix / docstring，长 Prompt 反复超时（run7 的 1079s GAP）
  - 同一份代码有时全绿、有时超时 → 「碰巧通过」而非「稳定通过」

修复位置：python_worker/intent_router/_router.py
  detect_intent() 内新增「文档-only 架构设计」确定性优先拦截，早于 LLM 语义路由。

本契约全部为本地秒级检查，不依赖任何 LLM 调用结果。
"""
import contextlib
import io
from pathlib import Path

from python_worker.intent_router import IntentRouter
from python_worker.tests import test_observe_task_system as obs

_ROOT = Path(__file__).resolve().parents[2]
_WORKER = _ROOT / "python_worker" / "agents" / "qwen" / "qwen_worker_v2.py"

ARCH_CHAIN_BANNED_STEPS = {"test", "fix", "docstring"}


def _detect_quiet(prompt):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return IntentRouter.detect_intent(prompt, "qwen")


def test_r5_classification_is_deterministic_across_repeats():
    """同一题面重复分类 10 次，不允许出现任何一次漂移。"""
    for i in range(10):
        intent, persona, chain = _detect_quiet(obs.PROMPT_ROUND_5)
        assert intent == "architecture", f"第 {i} 次分类漂移为 {intent}"
        assert persona == "architect", f"第 {i} 次人格漂移为 {persona}"
        assert not (ARCH_CHAIN_BANNED_STEPS & set(chain)), (
            f"第 {i} 次执行链混入无关步骤: {chain}"
        )


def test_deterministic_rule_matches_only_round5():
    """规则必须精准：只拦 R5，不得误伤 R6–R10 的正常编码/重构题。"""
    assert IntentRouter._is_architecture_document_request(obs.PROMPT_ROUND_5)
    for n in range(6, 11):
        prompt = getattr(obs, f"PROMPT_ROUND_{n}")
        assert not IntentRouter._is_architecture_document_request(prompt), (
            f"R{n} 被误判为文档-only 架构请求"
        )


def test_rule_requires_explicit_no_implementation_constraint():
    """只提「架构/设计」但要求实现的正常编码任务不得被拦截。"""
    assert not IntentRouter._is_architecture_document_request(
        "请设计 backend 架构，并实现订单模块，写出完整代码和单元测试"
    )
    assert not IntentRouter._is_architecture_document_request(
        "Design the system architecture and implement it in FastAPI"
    )
    # 文档-only 措辞（中/英）都应命中
    assert IntentRouter._is_architecture_document_request(
        "请输出架构设计文档，不要写任何实现代码"
    )
    assert IntentRouter._is_architecture_document_request(
        "Write an architecture design document only; do not write any implementation code"
    )


def test_architecture_chain_is_lean():
    """架构链固定为 7 步，不得混入 test/fix/docstring 这类烧时间的可选步骤。"""
    _, _, chain = _detect_quiet(obs.PROMPT_ROUND_5)
    assert chain == [
        "analyze", "workspace", "plan", "setup", "write", "refine", "doc"
    ]


def test_failure_repair_rule_matches_only_round7():
    """「pytest 报错 + 请修复」必须精准命中 R7，不得误伤其它五轮。"""
    assert IntentRouter._is_test_failure_repair_request(obs.PROMPT_ROUND_7)
    for n in (5, 6, 8, 9, 10):
        prompt = getattr(obs, f"PROMPT_ROUND_{n}")
        assert not IntentRouter._is_test_failure_repair_request(prompt), (
            f"R{n} 被误判为测试失败修复请求"
        )


def test_r7_classification_is_deterministic_and_lean():
    """R7 不得再漂移到 write_code；链必须走修复类精简链。"""
    for i in range(5):
        intent, persona, chain = _detect_quiet(obs.PROMPT_ROUND_7)
        assert intent == "fix_code", f"第 {i} 次分类漂移为 {intent}"
        assert "setup" not in chain and "doc" not in chain and "docstring" not in chain
        assert "write" in chain and "fix" in chain


def test_repair_intent_chain_drops_setup_and_document_steps():
    """修复类任务不得跑 setup/doc/docstring：这曾把 R7 拖过 900s 轮询窗口。"""
    for intent in ("fix_code", "explain_and_fix"):
        chain = IntentRouter.build_execution_chain(intent)
        assert "write" in chain and "test" in chain and "fix" in chain
        assert "setup" not in chain
        assert "doc" not in chain
        assert "docstring" not in chain
        assert len(chain) <= 7


def test_non_repair_code_chains_are_not_affected():
    """裁剪只针对修复类，正常建项目/重构链不得被误伤。"""
    for intent in ("write_code", "refactor"):
        chain = IntentRouter.build_execution_chain(intent)
        assert "setup" in chain
        assert "doc" in chain
        assert "docstring" in chain


def test_worker_captures_intent_input_before_memory_injection():
    """设计原则锁死：意图分类只能用干净的当前请求，不能吃记忆/会话注入。

    记忆注入是给生成步骤补上下文的；一旦参与分类，历史会话里的代码味
    文字会把架构题锚定到 write_code。worker_runtime.py 也是这么做的。
    """
    src = _WORKER.read_text(encoding="utf-8")
    i_original = src.index("original_prompt = prompt")
    i_intent = src.index("_intent_prompt = prompt")
    i_memory = src.index("enhance_prompt_with_memory(prompt, memory_ctx)")

    assert i_original < i_memory
    assert i_intent < i_memory
    # 只允许「正常分支」和「无文本的图片兜底」两处赋值，防止后续被增强 prompt 覆盖
    assert src.count("_intent_prompt =") == 2
    assert "detect_intent(_intent_prompt)" in src


# ── G10.23：枚举值级联修改的确定性兜底（shopflow_v4_1 / R9 实证） ──────

def test_r9_enum_cascade_is_write_code_even_when_classifier_down(monkeypatch):
    """分类 LLM 完全不可用时，R9 题面仍必须判 write_code，不能静默掉到 chat。

    真实故障：qwen-plus 免费额度耗尽(403) → 分类器单点无降级 → Regex 兜底
    未命中 → chat 链路（analyze→workspace→plan→respond）→ 零 FileOps、
    无授权记录，质量+治理双红并连锁 R10。
    """
    monkeypatch.setattr(IntentRouter, "_llm_classify", lambda *a, **k: None)
    intent, _persona, chain = _detect_quiet(obs.PROMPT_ROUND_9)
    assert intent == "write_code", intent
    assert "write" in chain, chain
    assert "respond" not in chain, chain


def test_enum_cascade_detector_does_not_misfire_on_other_rounds():
    """严格 FAIL-OPEN：架构文档 / 从零建项目 / 闲聊都不该被这条规则拦截。"""
    assert not IntentRouter._is_enum_cascade_change_request(
        obs.PROMPT_ROUND_5)
    assert not IntentRouter._is_enum_cascade_change_request("你好，今天天气怎么样")
    assert not IntentRouter._is_enum_cascade_change_request(
        "请从零创建一个电商订单项目并实现核心功能")
    assert not IntentRouter._is_enum_cascade_change_request(
        "请修改后端架构，把状态值画成一张图")  # 有实体+动词，无级联范围/映射
    assert IntentRouter._is_enum_cascade_change_request(obs.PROMPT_ROUND_9)


def test_r5_still_architecture_when_classifier_down(monkeypatch):
    """新增拦截必须排在架构文档识别之后，不能反过来误伤 R5。"""
    monkeypatch.setattr(IntentRouter, "_llm_classify", lambda *a, **k: None)
    intent, _persona, chain = _detect_quiet(obs.PROMPT_ROUND_5)
    assert intent == "architecture", intent
    assert not (ARCH_CHAIN_BANNED_STEPS & set(chain)), chain
