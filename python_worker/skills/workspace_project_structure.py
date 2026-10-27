# -*- coding: utf-8 -*-
"""workspace.project-structure Skill：读取项目并画出项目结构图。

职责声明：
  - 这是一个**只读能力 Skill**，不创建或修改任何文件。
  - 由 Capability Executor 扫描真实文件系统，LLM 不得编造目录结构。
  - 输出格式：ASCII 文本树 + Mermaid flowchart，直接呈现在对话中。
"""

from .base import Skill


def register(registry):
    registry.register(
        Skill(
            id="workspace.project-structure",
            name="项目结构可视化",
            version="1.0.0",
            description=(
                "读取当前工作区的真实目录结构，生成文本树和可交互的 Mermaid 结构图。"
                "完全基于文件系统扫描结果，不依赖 LLM 编造。"
            ),
            triggers=(
                "项目结构",
                "结构图",
                "目录结构",
                "画出结构",
                "文件结构",
                "项目树",
                "文件树",
                "展示结构",
                "项目目录",
                "架构图",
                "项目架构",
                "文件夹结构",
                "project structure",
                "directory tree",
                "file tree",
                "show structure",
                "visualize",
                "读取项目",
                "分析项目结构",
            ),
            priority=85,
            capabilities=("workspace.scan", "structure.tree", "structure.mermaid"),
            read_only=True,
            guidance=(
                "## 任务：展示项目结构图\n\n"
                "你正在处理一个**只读展示任务**。请严格遵循以下规则：\n\n"
                "1. **不要创建任何文件**——这是一次只读操作，唯一产出是对话中的可视化内容。\n"
                "2. **不要修改任何文件**——不要执行 write、edit、create 等文件操作。\n"
                "3. **使用系统提供的真实扫描结果**——所有目录和文件信息来自文件系统扫描，"
                "不是你的训练数据。如果提供了扫描结果，直接使用它，不要编造。\n"
                "4. **输出格式要求**：\n"
                "   - 先展示 ASCII 文本树（让用户看到层级关系）\n"
                "   - 再展示 Mermaid flowchart（如果提供了 Mermaid 源码，用 ```mermaid 代码块包裹）\n"
                "   - 最后附上简要的结构说明\n"
                "5. **如果系统提供了 capability 扫描结果**（_capability_results），"
                "直接在回答中引用这些结果，不要重新扫描或猜测。\n"
                "6. **如果没有提供扫描结果**，请明确告知用户"
                "并说明原因（工作区不可用 / 扫描失败等），然后询问是否接受基于项目文件的粗略分析。\n\n"
                "## 输出模板\n\n"
                "```text\n"
                "[在此粘贴 structure.tree 的结果]\n"
                "```\n\n"
                "```mermaid\n"
                "[在此粘贴 structure.mermaid 的结果]\n"
                "```\n\n"
                "## 结构概览\n"
                "[简要分析项目结构特点]\n"
            ),
        )
    )