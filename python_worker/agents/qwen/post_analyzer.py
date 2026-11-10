# -*- coding: utf-8 -*-
# post_analyzer.py
# ---------------------------------------------------------
# Post-Analyzer — analyze 步骤完成后的执行链重决策
#
# Responsibility:
#   - 从 analyze 步骤输出提取 ExecutionProfile
#   - vision_analysis 模式下推断有效意图
#   - 根据 LLM 分析结果重建剩余执行链
#   - Planning Contract 策略检查
#
# Extracted from qwen_worker_v2.py execute_task()
# ---------------------------------------------------------

from ...worker_config import stream_chunk
from ...intent_router import IntentRouter
from ...intent_router._data import INTENT_TO_PERSONA
from ...collaboration_modes import apply_mode_to_persona
from ...task_state_contract import (
    STEP_STATE_PENDING,
    STEP_STATE_COMPLETED,
)

from .step_executor import execute_step
from .execution_chain import create_steps_from_chain, filter_read_only_chain


def run_post_analyze(
    steps: list,
    task_id: str,
    events: list,
    context: dict,
    intent: str,
    persona_type: str,
    persona_config: dict,
    execution_plan: dict,
    prompt: str,
    original_prompt: str,
    payload: dict,
    task_type: str,
    mode: str,
    selected_skill,
    has_vision: bool,
    execution_chain: list,
):
    """
    analyze 步骤执行后，从 LLM 输出提取 ExecutionProfile，
    重建剩余执行链。
    ⭐ v4.3: 兼容 vision_analysis 作为第一步时，analyze 在第二步
    ⭐ v4.4: vision_analysis 已执行完毕，analyze 位于 idx=0

    Returns:
        (new_intent, new_persona_type, new_persona_config, new_execution_chain)
        如果无需重建则返回原值。
    """
    _analyze_idx = next(
        (i for i, s in enumerate(steps) if s.get("type") == "analyze"), -1
    )
    if _analyze_idx not in (0, 1):
        return intent, persona_type, persona_config, execution_chain

    analyze_step = steps.pop(_analyze_idx)
    analyze_step["status"] = "running"
    analysis_text = ""

    try:
        # ⭐ v4.4: 在 analyze prompt 中注入视觉上下文
        if context.get("_vision_result"):
            _orig_analyze_prompt = analyze_step.get("input", {}).get("prompt", "")
            analyze_step.setdefault("input", {})["prompt"] = (
                f"[视觉分析已完成，以下是分析结果作为事实参考]\n"
                f"{context['_vision_result']}\n\n"
                f"---\n\n[用户原始请求]\n{_orig_analyze_prompt}"
            )

        execute_step(task_id, analyze_step, events, context)
        analyze_step["status"] = STEP_STATE_COMPLETED

        analysis_text = analyze_step.get("output", {}).get("text", "")
        llm_profile = IntentRouter.parse_execution_profile_from_analysis(analysis_text)

        # ⭐ v4.4: vision_analysis → 从 LLM 分析推断有效意图
        if context.get("_vision_result") and llm_profile:
            intent, persona_type, persona_config, execution_plan = _infer_intent_from_vision(
                llm_profile, intent, persona_type, persona_config, execution_plan,
                context, mode, task_id,
            )

        if llm_profile and intent != "run_tests":
            new_chain = IntentRouter.build_execution_chain(
                intent, profile=llm_profile, worker="qwen"
            )
            new_chain = [s for s in new_chain if s != "analyze"]
            new_chain = filter_read_only_chain(new_chain, selected_skill)

            if new_chain != [
                s["type"] for s in steps
                if s.get("type") in (
                    "plan", "workspace", "write", "refine", "test", "fix",
                    "doc", "docstring", "respond", "profile", "optimize",
                )
            ]:
                old_chain = [s["type"] for s in steps]
                steps.clear()

                # 重建 chain 时保留 vision_analysis
                if has_vision:
                    steps.append({
                        "id": "step-0",
                        "type": "vision_analysis",
                        "status": STEP_STATE_PENDING,
                        "input": {
                            "prompt": original_prompt,
                            "images": payload.get("images", []),
                            "model_type": task_type,
                            "workspace_path": payload.get("workspace_path", "."),
                        },
                    })
                steps.extend(create_steps_from_chain(new_chain, prompt, persona_type, intent))
                from ...collaboration_modes import apply_mode_to_steps
                apply_mode_to_steps(steps, mode)

                _display_chain = (
                    (["vision_analysis"] if has_vision else []) + ["analyze"] + new_chain
                )
                context["meta"]["execution_chain"] = _display_chain
                context["meta"]["execution_plan"]["execution_chain"] = _display_chain
                execution_chain = _display_chain

                print(
                    f"\n🔄 [v4.0] LLM 分析重定向: "
                    f"{' → '.join(old_chain)} → {' → '.join(new_chain)}"
                )
                if task_id:
                    stream_chunk(
                        task_id,
                        f"🔄 LLM 分析结果调整了执行计划：{' → '.join(new_chain)}\n",
                        phase="routing",
                        channel="reasoning",
                    )

    except Exception as e:
        if "EvidenceGate" in type(e).__name__:
            raise
        print(f"[WARN] Post-analyze 重决策失败: {e}")
        steps.insert(_analyze_idx, analyze_step)
    else:
        context.setdefault("intermediate_results", []).append({
            "type": "analyze",
            "analysis": analysis_text,
            "llm_success": True,
        })

    return intent, persona_type, persona_config, execution_chain


def _infer_intent_from_vision(
    llm_profile,
    intent: str,
    persona_type: str,
    persona_config: dict,
    execution_plan: dict,
    context: dict,
    mode: str,
    task_id: str,
):
    """从视觉 LLM 分析结果推断有效意图。"""
    if llm_profile.output_mode == "code" and llm_profile.requires_fileops:
        effective_intent = "explain_and_fix"
    elif llm_profile.output_mode == "code":
        effective_intent = "explain_code"
    elif llm_profile.workspace_dependency in ("read_write",):
        effective_intent = "write_code"
    else:
        effective_intent = "chat"

    if effective_intent == intent:
        return intent, persona_type, persona_config, execution_plan

    # Planning Contract: 重规划策略检查
    from ...intent_router._planning_contract import validate_replan, needs_reauthorization
    _allowed, _reason = validate_replan(intent, effective_intent)
    if not _allowed:
        print(f"\n⛔ [Planning Contract] 重规划策略阻止: {_reason}")
        return intent, persona_type, persona_config, execution_plan

    if _reason:
        print(f"\n⚠️ [Planning Contract] {_reason}")
    if needs_reauthorization(intent, effective_intent):
        print(f"🔐 [Planning Contract] {intent} → {effective_intent} 需重新授权")

    intent = effective_intent
    persona_type = INTENT_TO_PERSONA.get(effective_intent, "engineer")
    persona_config = apply_mode_to_persona(persona_config, mode)

    execution_plan["intent"] = intent
    execution_plan["persona"] = persona_type
    context["meta"].update({
        "intent": intent,
        "persona": persona_type,
        "persona_config": persona_config,
    })

    print(
        f"\n🔄 [Post-analyze v4.4] 意图推断: vision → {intent}"
    )
    print(f"   新人格: {persona_config['name']} ({persona_config['icon']})")
    if task_id:
        stream_chunk(
            task_id,
            f"\n🔍 图片分析完成，推断任务意图: {intent}\n",
            phase="routing",
            channel="reasoning",
        )

    return intent, persona_type, persona_config, execution_plan