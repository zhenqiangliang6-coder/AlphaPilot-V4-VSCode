# -*- coding: utf-8 -*-
# skills/creative_pure_text.py — 纯文本创作技能
# ---------------------------------------------------------

from .base import Skill


def register(registry):
    registry.register(
        Skill(
            id="creative.pure-text",
            name="Pure Creative Text Generation",
            version="1.0.0",
            description="纯文本创作：诗歌、故事、散文、歌词、翻译等，不依赖项目上下文，不生成文件。",
            triggers=(
                "写诗", "写一首", "作一首", "创作一首", "写首", "作首",
                "写故事", "写散文", "写歌词", "写小说", "写文章",
                "翻译", "translation", "translate",
                "写一段", "写一句", "写个笑话", "写对联",
                "现代诗", "古诗", "自由诗", "格律诗",
                "poem", "poetry", "story", "lyrics", "novel",
            ),
            priority=75,
            capabilities=(
                "output.text",
            ),
            output_profile={
                "output_mode": "text",
                "workspace_dependency": "none",
                "target_format": "plain_text",
                "requires_fileops": False,
                "requires_workspace_scan": False,
            },
            guidance=(
                "直接创作文本内容，保持文学性和流畅性。"
                "不生成代码文件、不分析项目代码、不运行测试、不扫描工作区。"
                "输出纯自然语言文本，无 FileOps。"
                "如果用户主题涉及项目，如需要了解项目则可斟酌是否读取工作区。"
            ),
        )
    )