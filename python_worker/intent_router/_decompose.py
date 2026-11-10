# -*- coding: utf-8 -*-
# intent_router._decompose — 复合请求分解器
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - 所有分解逻辑在 Worker 内部执行
#    - LLM 调用的分解结果由 Worker 独裁决断
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - Phase 协议保持不变：每个子任务独立走 detect_intent → execution_chain
#    - 不引入新的端点到 Extension 或 Webview
#
# 设计原则：
#   1. 零侵入 — 不改变 detect_intent 现有签名
#   2. 一次 LLM 调用 — 分类 + 分解同一次 API 调用完成
#   3. 1% 级影响 — 仅当 LLM 判定 is_compound=true 时走多阶段路径
#   4. 降级安全 — 任何分解失败自动回退单阶段执行
#
# ---------------------------------------------------------

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Phase:
    """单个子任务阶段。

    LLM 输出格式中的 phases[i] 对应一个执行阶段。

    字段:
        type: 意图类型（write_code / execute_operation / generate_doc / refactor）
        prompt: 该阶段的子提示词
    """
    type: str
    prompt: str
    target_language: str = ""  # python | java | javascript | typescript — 跨 Worker 编排用

    def __post_init__(self):
        if not isinstance(self.type, str) or not self.type.strip():
            raise ValueError(f"Phase.type 不能为空: {self.type!r}")
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise ValueError(f"Phase.prompt 不能为空: {self.prompt!r}")


@dataclass
class CompoundPlan:
    """复合请求执行计划。

    字段:
        is_compound: 是否为复合请求
        phases: 子任务阶段列表（有序）
        fallback_intent: 非复合时的回退单意图
        fallback_persona: 非复合时的回退人格
        fallback_chain: 非复合时的回退执行链

    示例:
        CompoundPlan(
            is_compound=True,
            phases=[
                Phase(type="write_code", prompt="写一个登录功能并更新CHANGELOG"),
                Phase(type="execute_operation", prompt="上传到GitHub"),
            ],
        )
    """
    is_compound: bool
    phases: List[Phase] = field(default_factory=list)
    fallback_intent: str = ""
    fallback_persona: str = ""
    fallback_chain: List[str] = field(default_factory=list)

    def validate(self) -> bool:
        """验证计划完整性。

        复合计划必须有至少两个阶段且所有阶段类型有效。
        非复合计划必须有有效的回退意图。
        """
        if self.is_compound:
            if len(self.phases) < 2:
                return False
            valid_types = {
                "write_code", "execute_operation", "generate_doc",
                "refactor", "fix_code", "analysis",
            }
            return all(p.type in valid_types for p in self.phases)
        else:
            return bool(self.fallback_intent)

    def to_single(self) -> tuple:
        """转换为单阶段 (intent, persona, chain) 元组。"""
        if self.is_compound:
            raise RuntimeError("复合计划不能转换为单阶段")
        return (self.fallback_intent, self.fallback_persona, self.fallback_chain)

    @classmethod
    def from_llm_result(cls, llm_result: Optional[dict], fallback_fn) -> "CompoundPlan":
        """从 LLM classify 结果构造 CompoundPlan。

        参数:
            llm_result: llm_classify 的返回字典
            fallback_fn: 无参数函数，返回 (intent, persona, chain)
        """
        if llm_result and llm_result.get("is_compound"):
            raw_phases = llm_result.get("phases")
            if isinstance(raw_phases, list) and len(raw_phases) >= 2:
                try:
                    phases = []
                    for p in raw_phases:
                        if isinstance(p, dict) and "type" in p and "prompt" in p:
                            phases.append(Phase(
                                type=p["type"].strip(),
                                prompt=p["prompt"].strip(),
                                target_language=p.get("target_language", "").strip(),
                            ))
                    if len(phases) >= 2:
                        print(f"\n🔀 CompoundDecomposer: {len(phases)} 阶段复合请求")
                        for i, ph in enumerate(phases):
                            print(f"   阶段 {i + 1}: [{ph.type}] {ph.prompt[:60]}")
                        return cls(is_compound=True, phases=phases)
                except Exception as e:
                    print(f"\n⚠️ CompoundDecomposer: 解析 phases 失败 ({e})，降级单阶段")

        fallback = fallback_fn()
        return cls(
            is_compound=False,
            fallback_intent=fallback[0],
            fallback_persona=fallback[1],
            fallback_chain=list(fallback[2]),
        )