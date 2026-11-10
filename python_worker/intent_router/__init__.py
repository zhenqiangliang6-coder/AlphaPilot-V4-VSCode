# -*- coding: utf-8 -*-
# intent_router 包 — 向后兼容入口
# 所有原有 import 路径保持不变
from ._router import IntentRouter, detect_user_intent, requires_authorization_before_step

# G8.0: 复合请求分解器
from ._decompose import Phase, CompoundPlan

# G8.2: 多语言执行链配置
from ._chains import (
    LANGUAGE_FORMAT_MAP,
    LANGUAGE_CHAINS,
    LanguageStepModifier,
    get_language_format,
    get_language_modifier,
    apply_language_modifiers,
)

__all__ = [
    "IntentRouter",
    "detect_user_intent",
    "requires_authorization_before_step",
    "Phase",
    "CompoundPlan",
    "LANGUAGE_FORMAT_MAP",
    "LANGUAGE_CHAINS",
    "LanguageStepModifier",
    "get_language_format",
    "get_language_modifier",
    "apply_language_modifiers",
]