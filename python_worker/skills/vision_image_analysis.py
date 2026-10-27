# -*- coding: utf-8 -*-
# skills/vision_image_analysis.py — 图片分析与理解技能
# ---------------------------------------------------------

from .base import Skill


def register(registry):
    registry.register(
        Skill(
            id="vision.image-analysis",
            name="Image Analysis & Understanding",
            version="1.0.0",
            description="图片/截图分析与理解：UI截图→代码、错误截图→诊断、架构图→分析、设计稿→前端代码。",
            triggers=(
                "看图", "分析图片", "这张图", "那个图",
                "截图", "屏幕截图", "UI截图", "界面截图",
                "设计稿", "设计图", "原型图", "mockup",
                "screenshot", "image", "图片理解",
                "识别图中", "识别图片", "图片里",
                "照片", "拍照", "看图说话",
                "报错截图", "错误截图", "调试截图",
                "架构图", "流程图", "UML图", "ER图",
                "图表", "数据图", "统计图",
            ),
            priority=85,
            capabilities=(
                "vision.read",
                "output.analysis",
                "output.text",
            ),
            output_profile={
                "output_mode": "code",
                "workspace_dependency": "read_write",
                "target_format": "py",
                "requires_fileops": True,
                "requires_workspace_scan": True,
                "requires_test": True,
                "estimated_complexity": "moderate",
            },
            guidance=(
                "接收用户上传的图片/截图，进行视觉内容识别和分析。"
                "适用场景："
                "  - UI截图 → 分析布局结构，可生成对应前端代码"
                "  - 报错截图 → 提取错误信息，结合工作区诊断"
                "  - 架构图 → 理解系统结构，输出分析报告"
                "  - 设计稿 → 理解视觉设计，生成实现方案"
                "  - 数据图表 → 提取数据结论"
                "如果是代码相关图片（报错/UI/架构），可结合工作区上下文给出操作建议。"
                "如果是纯视觉内容（照片/图表），给出自然语言描述和分析。"
            ),
        )
    )