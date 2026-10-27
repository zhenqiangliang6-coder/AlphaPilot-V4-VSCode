# -*- coding: utf-8 -*-
"""architecture.analyzer Skill：深度分析项目代码结构，生成架构图。

职责声明：
  - 这是一个**只读能力 Skill**，不创建或修改任何文件。
  - 分析源码 import 依赖、类/函数定义，推断架构分层。
  - 输出 Mermaid 架构图 + ASCII 分层图 + 风险报告。
  - 与 workspace.project-structure 互补：后者展示文件树，前者展示逻辑架构。
"""

from .base import Skill


def register(registry):
    registry.register(
        Skill(
            id="architecture.analyzer",
            name="架构深度分析",
            version="1.0.0",
            description=(
                "深度分析项目源码结构，提取模块依赖关系、类/函数定义、"
                "推断架构分层、检测循环依赖和架构风险。"
                "输出 Mermaid 架构图、ASCII 分层图和风险报告。"
            ),
            triggers=(
                "架构图",
                "项目架构",
                "架构分析",
                "画架构",
                "系统架构",
                "代码结构",
                "依赖关系",
                "模块依赖",
                "架构设计",
                "画项目架构",
                "查看项目画架构",
                "项目架构图",
                "architecture diagram",
                "system architecture",
                "dependency graph",
                "module structure",
                "代码架构",
                "分析架构",
            ),
            priority=90,
            capabilities=("arch.analyze", "workspace.scan", "structure.tree", "structure.mermaid"),
            read_only=True,
            guidance=(
                "## 任务：深度架构分析\n\n"
                "你正在处理一个**只读架构分析任务**。请严格遵循以下规则：\n\n"
                "1. **不要创建任何文件**——这是一次只读操作。\n"
                "2. **不要修改任何文件**——不要执行 write、edit、create 等文件操作。\n"
                "3. **使用系统提供的架构分析结果**——所有模块、依赖、分层信息来自源码扫描，"
                "不是你的训练数据。\n"
                "4. **输出格式要求**（按顺序）：\n"
                "   a) 项目架构概述（项目类型、技术栈、规模）\n"
                "   b) ASCII 分层架构图（展示模块职责和层级关系）\n"
                "   c) Mermaid 架构图（展示模块依赖关系）\n"
                "   d) 关键依赖关系说明\n"
                "   e) 架构风险与改进建议\n"
                "5. **如果系统提供了 _capability_results.arch.analyze**，"
                "直接引用其中的 mermaid_diagram 和 ascii_diagram。\n"
                "6. **架构分层说明**：解释为什么某些模块属于特定层次。\n"
                "7. **只读约束**：不生成应用代码、不运行测试、不修改配置。"
            ),
        )
    )