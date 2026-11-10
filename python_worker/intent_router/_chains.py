# -*- coding: utf-8 -*-
# intent_router._chains — Per-language execution chain configuration
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相
#    执行链定义是 Worker 的核心决策，不暴露到协议层
#
# ✅ 协议 = 宪法
#    所有语言共享同一个 Intent → Profile → Chain 管道
#    差异仅在步骤集合：编译型语言多 compile 步骤
#
# 本模块是"多语言横向扩展"的基石：
# - 每种语言在此注册其执行链差异
# - 新增语言 = 新增一个 LANGUAGE_CHAINS 条目
# - 零侵入：默认语言=python，100% 向后兼容
#
# ---------------------------------------------------------

from typing import Dict, List, Optional
from dataclasses import dataclass, field


# ============================================================
# Language → target_format 映射
# ============================================================
LANGUAGE_FORMAT_MAP: Dict[str, str] = {
    "python":     "py",
    "java":       "java",
    "nodejs":     "js",
    "typescript": "ts",
    "go":         "go",
    "rust":       "rs",
    "c":          "c",
    "cpp":        "cpp",
    "csharp":     "cs",
    "kotlin":     "kt",
    "swift":      "swift",
    "ruby":       "rb",
    "php":        "php",
}


# ============================================================
# Per-language step modifiers
# ============================================================
@dataclass
class LanguageStepModifier:
    insert_after: Dict[str, List[str]] = field(default_factory=dict)
    remove_steps: List[str] = field(default_factory=list)
    reorder: Dict[str, int] = field(default_factory=dict)


LANGUAGE_CHAINS: Dict[str, LanguageStepModifier] = {
    "python": LanguageStepModifier(),
    "java": LanguageStepModifier(
        insert_after={
            "write": ["compile"],
        },
    ),
    "nodejs": LanguageStepModifier(),
    "typescript": LanguageStepModifier(
        insert_after={
            "write": ["compile"],
        },
    ),
    "go": LanguageStepModifier(
        insert_after={
            "write": ["compile"],
        },
    ),
    "rust": LanguageStepModifier(
        insert_after={
            "write": ["compile"],
        },
    ),
    "c": LanguageStepModifier(
        insert_after={
            "write": ["compile"],
        },
    ),
    "cpp": LanguageStepModifier(
        insert_after={
            "write": ["compile"],
        },
    ),
    "csharp": LanguageStepModifier(
        insert_after={
            "write": ["compile"],
        },
    ),
    "kotlin": LanguageStepModifier(
        insert_after={
            "write": ["compile"],
        },
    ),
    "swift": LanguageStepModifier(
        insert_after={
            "write": ["compile"],
        },
    ),
}


def get_language_format(language: str) -> str:
    return LANGUAGE_FORMAT_MAP.get(language, "plain_text")


def get_language_modifier(language: str) -> LanguageStepModifier:
    return LANGUAGE_CHAINS.get(language, LANGUAGE_CHAINS["python"])


def apply_language_modifiers(chain: List[str], language: str) -> List[str]:
    modifier = get_language_modifier(language)

    if modifier.remove_steps:
        chain = [s for s in chain if s not in modifier.remove_steps]

    for anchor, insert_steps in modifier.insert_after.items():
        if anchor in chain:
            idx = chain.index(anchor)
            for i, step in enumerate(insert_steps):
                chain.insert(idx + 1 + i, step)

    return chain