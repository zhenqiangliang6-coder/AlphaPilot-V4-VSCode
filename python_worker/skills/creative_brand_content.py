# -*- coding: utf-8 -*-
# skills/creative_brand_content.py — 品牌文案创作技能
# ---------------------------------------------------------

from .base import Skill


def register(registry):
    registry.register(
        Skill(
            id="creative.brand-content",
            name="Brand & Marketing Content Generation",
            version="1.0.0",
            description="品牌文案创作：slogan、宣传语、广告文案、产品描述。需了解项目但不生成文件。",
            triggers=(
                "slogan", "标语", "口号", "品牌文案",
                "宣传语", "广告文案", "推广文案", "营销文案",
                "产品描述", "产品介绍文案", "卖点",
                "品牌故事", "品牌定位", "品牌调性",
                "文案", "软文", "PR稿", "新闻稿",
                "brand", "marketing", "copywriting",
            ),
            priority=70,
            capabilities=(
                "workspace.read",
                "output.text",
            ),
            output_profile={
                "output_mode": "text",
                "workspace_dependency": "read_only",
                "target_format": "plain_text",
                "requires_fileops": False,
                "requires_workspace_scan": True,
            },
            guidance=(
                "先了解项目定位、功能特点和目标用户，再生成贴合项目的品牌文案。"
                "输出纯文本，不创建文件。"
                "文案风格应匹配项目调性：技术产品偏向专业简洁，消费产品偏向情感共鸣。"
                "可提供多个版本供用户选择。"
            ),
        )
    )