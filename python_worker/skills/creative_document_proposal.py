# -*- coding: utf-8 -*-
# skills/creative_document_proposal.py — 项目感知型文档创作技能
# ---------------------------------------------------------

from .base import Skill


def register(registry):
    registry.register(
        Skill(
            id="creative.document-proposal",
            name="Project-Aware Document & Proposal Generation",
            version="1.0.0",
            description="项目感知型文档创作：招商方案、PRD、技术方案、商业计划书等。需读取项目文件，生成 Markdown 文档。",
            triggers=(
                "招商方案", "招商计划", "商业计划书", "BP",
                "PRD", "产品需求文档", "需求规格说明书",
                "技术方案", "技术设计文档", "架构方案书",
                "proposal", "pitch deck", "pitch",
                "项目介绍", "产品介绍", "公司介绍",
                "解决方案", "方案书", "标书",
                "融资计划", "商业模型",
            ),
            priority=80,
            capabilities=(
                "workspace.read",
                "workspace.scan",
                "fileops.create",
                "output.document",
            ),
            output_profile={
                "output_mode": "document",
                "workspace_dependency": "read_only",
                "target_format": "markdown",
                "requires_fileops": True,
                "requires_workspace_scan": True,
            },
            guidance=(
                "先扫描项目结构和代码，理解项目功能、架构和技术栈后再生成文档。"
                "文档以 Markdown 格式写入工作区。"
                "招商/商业类文档需包含：项目概述、技术架构、市场分析、商业模式、团队介绍等。"
                "技术方案需包含：架构设计、技术选型、模块划分、接口设计、部署方案等。"
                "不修改现有代码文件。"
            ),
        )
    )