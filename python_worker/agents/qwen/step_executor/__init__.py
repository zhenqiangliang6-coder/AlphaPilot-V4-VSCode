# -*- coding: utf-8 -*-
# step_executor/__init__.py
# ---------------------------------------------------------
# 多步骤执行器模块（analyze / plan / write / refine / test / fix / profile / doc / docstring）
# 统一导出所有公共 API，供 Worker 调用
# ---------------------------------------------------------

# ---------------------------------------------------------
# 核心步骤执行函数
# ---------------------------------------------------------
from .analyze_step import run_analyze_step
from .plan_step import run_plan_step
from .write_step import run_write_step
from .refine_step import run_refine_step

# ---------------------------------------------------------
# 扩展步骤执行函数
# ---------------------------------------------------------
from .test_step import run_test_step
from .fix_step import run_fix_step
from .profile_step import run_profile_step
from .doc_step import run_doc_step
from .docstring_step import run_docstring_step   # ⭐ v3.0: docstring 步骤
from .operate_step import run_operate_step       # ⭐ G7.0: operate 步骤
from .changelog_step import run_changelog_step   # ⭐ G8.0: changelog 步骤
from .setup_step import run_setup_step           # ⭐ P2: setup 步骤
from .compile_step import run_compile_step       # ⭐ G9: compile 步骤（语言工具链调度）
from .verification_governor import VerificationGovernor  # ⭐ G10: 智能验证治理

# ---------------------------------------------------------
# 统一步骤调度器（★ Worker 调用的唯一入口）
# ---------------------------------------------------------
from .execute_step import execute_step

# ---------------------------------------------------------
# 工具函数 & 常量
# ---------------------------------------------------------
from .utils import extract_code, FAKE_ENVIRONMENT
from ..qwen_api import call_llm


# ---------------------------------------------------------
# Prompt 模板（10 个）
# ---------------------------------------------------------
from .prompts import (
    analyze_prompt,
    plan_prompt,
    write_prompt,
    refine_prompt,
    test_prompt,
    fix_prompt,
    profile_prompt,
    doc_prompt,
    docstring_prompt,
    optimize_prompt
)

# ---------------------------------------------------------
# 模块对外公开的 API
# ---------------------------------------------------------
__all__ = [
    # 核心步骤执行函数
    "run_analyze_step",
    "run_plan_step",
    "run_write_step",
    "run_refine_step",

    # 扩展步骤执行函数
    "run_test_step",
    "run_fix_step",
    "run_profile_step",
    "run_doc_step",
    "run_docstring_step",  # ⭐ v3.0: docstring 步骤
    "run_operate_step",   # ⭐ G7.0: operate 步骤
    "run_changelog_step", # ⭐ G8.0: changelog 步骤
    "run_setup_step",    # ⭐ P2: setup 步骤
    "run_compile_step",  # ⭐ G9: compile 步骤（语言工具链调度）

    # 智能验证治理
    "VerificationGovernor",  # ⭐ G10: 验证治理（Shadow Mode）

    # 统一步骤调度器（Worker 只需要调用这个）
    "execute_step",

    # 工具函数
    "extract_code",

    # API 调用
    "call_llm",

    # 常量
    "FAKE_ENVIRONMENT",

    # Prompt 模板 - 核心步骤
    "analyze_prompt",
    "plan_prompt",
    "write_prompt",
    "refine_prompt",

    # Prompt 模板 - 扩展步骤
    "test_prompt",
    "fix_prompt",
    "profile_prompt",
    "doc_prompt",
    "docstring_prompt",
    "optimize_prompt",
]