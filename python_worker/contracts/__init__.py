# -*- coding: utf-8 -*-
# python_worker/contracts/__init__.py
# ---------------------------------------------------------
# AlphaPilot Agent Runtime Architecture v1 契约定义
#
# 三大契约：
#   Skill Contract        — 定义能力、输入输出、证据要求、成功判定
#   Project Metadata      — 描述项目的技术特征及其来源与置信度
#   CommandExecutor       — 定义安全执行边界（在 command_executor.py 中实现）
#
# 七条架构原则：
#   1. Worker 负责思考，Capability 负责行动，Executor 负责治理
#   2. 能力契约 > 语言识别 — 不因语言不同而复制 Agent 生命周期
#   3. 统一执行入口 — 所有副作用操作经过 CommandExecutor
#   4. 证据即证明 — exit_code=0 ≠ 任务完成
#   5. 元数据可溯源 — 区分检测结论、LLM 推断和人工标注
#   6. 渐进迁移 — 旧 Worker 通过委托接入，不推倒重来
#   7. 权限不跟随模型 — CodingWorker 的计划不等于执行授权
# ---------------------------------------------------------

from .skill_contract import (
    SkillContract,
    SkillResult,
    EvidenceSet,
    EvidencePolicy,
    SuccessCriteria,
    SkillStatus,
    EvidenceRequirement,
)

from .project_metadata import (
    ProjectMetadata,
    MetadataSource,
    MetadataConfidence,
    BuildSystem,
    TestFramework,
    detect_project_metadata,
    update_project_metadata,
)

__all__ = [
    # Skill
    "SkillContract", "SkillResult", "EvidenceSet",
    "EvidencePolicy", "SuccessCriteria", "SkillStatus", "EvidenceRequirement",
    # Project
    "ProjectMetadata", "MetadataSource", "MetadataConfidence",
    "BuildSystem", "TestFramework",
    "detect_project_metadata", "update_project_metadata",
]