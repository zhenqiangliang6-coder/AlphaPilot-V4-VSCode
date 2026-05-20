# -*- coding: utf-8 -*-
# step_executor/prompts.py
# ---------------------------------------------------------
# 所有步骤类型的 prompt 模板（v3.0 执行链版）
# ⭐ v3.5 新增：上下文记忆注入功能
# ---------------------------------------------------------

import json

__all__ = [
    # 核心步骤 prompt
    "analyze_prompt",
    "plan_prompt",
    "write_prompt",
    "refine_prompt",
    
    # 扩展步骤 prompt
    "test_prompt",
    "fix_prompt",
    "profile_prompt",
    "doc_prompt",
    "docstring_prompt",
    "optimize_prompt",

    # ⭐ v2.8 新增
    "optimize_prompt_v28",
    
    # ⭐ v3.5 新增：上下文记忆注入
    "inject_memory_context",
]


def inject_memory_context(context: dict) -> str:
    """
    ⭐ v3.5 新增：将上下文记忆注入到 system prompt
    
    Args:
        context: 完整的任务上下文（包含 memory 字段）
        
    Returns:
        格式化后的记忆上下文字符串，如果没有记忆则返回空字符串
    """
    if not context or "memory" not in context:
        return ""
    
    memory = context["memory"]
    parts = []
    
    # 1. 项目上下文
    project_ctx = memory.get("project_context", {})
    if project_ctx:
        parts.append("\n\n【项目信息】")
        if project_ctx.get("name"):
            parts.append(f"- 项目名称: {project_ctx['name']}")
        if project_ctx.get("tech_stack"):
            tech_stack_str = json.dumps(project_ctx["tech_stack"], ensure_ascii=False)
            parts.append(f"- 技术栈: {tech_stack_str}")
        if project_ctx.get("metadata"):
            metadata_str = json.dumps(project_ctx["metadata"], ensure_ascii=False)
            parts.append(f"- 元数据: {metadata_str}")
    
    # 2. 用户偏好
    memory_ctx = memory.get("memory_context", {})
    user_prefs = memory_ctx.get("user_preferences", {})
    if user_prefs:
        parts.append("\n\n【用户偏好】")
        for key, value in user_prefs.items():
            parts.append(f"- {key}: {value}")
    
    # 3. 项目规则（最重要，放在前面）
    project_memories = memory_ctx.get("project_memories", [])
    if project_memories:
        parts.append("\n\n【项目规则】⭐ 必须严格遵守")
        for mem in sorted(project_memories, key=lambda x: x.get("importance", 0), reverse=True):
            importance_star = "⭐" * mem.get("importance", 3)
            parts.append(f"- {importance_star} {mem['content']}")
    
    # 4. 相似任务参考
    similar_tasks = memory_ctx.get("similar_tasks", [])
    if similar_tasks:
        parts.append("\n\n【相似任务参考】")
        for i, task in enumerate(similar_tasks[:3], 1):
            parts.append(f"{i}. 任务: {task['prompt'][:100]}...")
            if task.get("result_summary"):
                parts.append(f"   结果: {task['result_summary'][:100]}...")
            # 如果有步骤输出，展示关键信息
            if task.get("steps"):
                for step in task["steps"][:1]:
                    if step.get("output"):
                        output_preview = str(step["output"])[:150]
                        parts.append(f"   关键输出: {output_preview}...")
    
    # 5. 最近任务历史
    recent_tasks = memory_ctx.get("recent_tasks", [])
    if recent_tasks:
        parts.append("\n\n【最近任务历史】")
        for i, task in enumerate(recent_tasks[:3], 1):
            parts.append(f"{i}. {task['prompt'][:80]}...")
            if task.get("result_summary"):
                parts.append(f"   结果: {task['result_summary'][:80]}...")
    
    return "\n".join(parts)


def analyze_prompt(user_input: str, context: dict = None) -> str:
    """
    ⭐ v3.5 修改：支持上下文记忆注入
    """
    memory_context = inject_memory_context(context) if context else ""
    
    return f"""{memory_context}

请分析下面的任务描述，并提取关键需求点：

【用户任务描述】：
{user_input}

请输出：
1. 任务的核心目标
2. 需要实现的功能点
3. 输入与输出要求
4. 可能的边界情况
5. 需要注意的风险点

请使用结构化的自然语言，不要生成代码。
"""


def plan_prompt(analysis: str) -> str:
    return f"""
下面是对任务的分析结果，请根据这些内容生成代码结构规划：

【分析结果】：
{analysis}

请输出：
1. 代码的整体结构（模块/函数/类）
2. 每个函数的职责
3. 输入与输出设计
4. 伪代码（如果有必要）
5. 需要注意的边界情况

请使用自然语言描述，不要生成完整代码。
"""


def write_prompt(plan: str, context: dict = None) -> str:
    """
    ⭐ v3.5 修改：write 步骤的 prompt，支持上下文记忆注入
    
    write 步骤的 prompt：根据规划生成代码（多文件协议 v3.0）
    """
    memory_context = inject_memory_context(context) if context else ""
    
    return f"""{memory_context}

你现在处于 AlphaPilot OS v3.0 环境。

请严格按照以下"多文件输出协议"生成代码：

==========================
# FILE: <相对路径>
<代码内容>

# TEST: <测试文件路径>
<测试代码内容>

# DOC: <文档路径>
<文档内容>

# META:
{{"version": "1.0", "author": "AlphaPilot"}}

# DEPENDS:
{{"requirements": ["numpy>=1.20"]}}
==========================

【代码规划】：
{plan}

⭐⭐⭐ 强制要求（必须遵守）：

1. 必须使用 "# FILE:" 开头声明文件路径  
   - 格式：# FILE: sorter/__init__.py
   - 路径必须是相对路径，从项目根目录开始
   
2. 每个文件必须单独一个 # FILE: 块  
   - 不要将多个文件合并到一个块中
   - 每个文件之间用空行分隔
   
3. 支持新协议：
   - # TEST: 用于生成单元测试
   - # DOC: 用于生成文档说明
   - # META: 用于声明元数据（JSON格式）
   - # DEPENDS: 用于声明依赖（JSON格式）
   
4. 不得省略 # FILE:  
   - Worker 将根据 # FILE: 自动生成 FileOps
   - 没有 # FILE: 会导致多文件功能失效
   
5. 不得输出未声明路径的代码  
   - 所有代码必须在 # FILE: 块内
   
6. 文件路径示例：
   - sort_module/__init__.py
   - tests/test_sort_engine.py
   - docs/README.md

7. 代码质量要求：
   - 代码必须可运行
   - 变量命名清晰
   - 逻辑结构与规划一致
   - 包含必要的注释和文档字符串

只输出多文件协议内容，不要任何解释性文字。
"""


def refine_prompt(code: str, exec_summary: str) -> str:
    """
    旧版 refine（单文件为主，兼容多文件提示）
    """
    return f"""
下面是一段 Python 代码及其执行结果，请在保持语义不变的前提下优化代码。

【原始代码】：
\\`\\`\\`python
{code}
\\`\\`\\`

【执行结果】：
{exec_summary}

要求：
1. 在保证语义不变的前提下优化代码
2. 输出优化后的完整代码（使用 \\`\\`\\`python 代码块）
3. 如果你发现这是多文件项目，请优先使用 v3.0 协议（# FILE:, # TEST:, # DOC:, # META:, # DEPENDS:）
4. 不要输出任何解释性文字。
"""


def test_prompt(code: str) -> str:
    return f"""
下面是一段 Python 代码，请你为它生成 pytest 风格的单元测试代码。

【被测试代码】：
\\`\\`\\`python
{code}
\\`\\`\\`

要求：
1. 使用 pytest 风格（assert + pytest.raises）
2. 不要 import pytest（Worker 会自动注入 fake pytest）
3. 覆盖正常情况、边界情况、异常情况
4. 包含清晰的断言
5. 输出完整的测试代码（使用 \\`\\`\\`python 代码块）
6. 输出必须是合法 Python 代码，不要包含解释性文字。
"""


def fix_prompt(code: str, error_message: str) -> str:
    return f"""
下面是一段 Python 代码和它的执行错误，请分析错误原因并给出修复后的完整代码。

【原始代码】：
\\`\\`\\`python
{code}
\\`\\`\\`

【执行错误】：
{error_message}

要求：
1. 分析错误的根本原因
2. 给出修复后的完整代码（使用 \\`\\`\\`python 代码块）
3. 简要说明修复了什么问题（可以用注释形式写在代码里）
4. 不要输出解释性自然语言。
"""


def profile_prompt(code: str) -> str:
    return f"""
请对下面的 Python 代码进行性能分析：

【代码】：
\\`\\`\\`python
{code}
\\`\\`\\`

请分析：
1. 时间复杂度（大 O 表示法）
2. 空间复杂度
3. 性能瓶颈在哪里
4. 如何优化（给出具体的优化建议）
5. 如果可能，提供优化后的代码示例

输出为结构化自然语言分析，不要生成代码。
"""


def doc_prompt(code: str) -> str:
    return f"""
请为下面的 Python 代码生成完整的文档：

【代码】：
\\`\\`\\`python
{code}
\\`\\`\\`

请生成：
1. 模块级别的文档字符串说明
2. 每个函数的完整文档（参数、返回值、异常）
3. 类的文档（如果有类）
4. 使用示例代码（用 \\`\\`\\`python 代码块包裹）
5. 注意事项

输出必须是合法 Markdown 文档，不要包含多余解释性文字。
"""


def docstring_prompt(code: str) -> str:
    return f"""
请在下面这段 Python 代码中添加完整的文档字符串（docstring），保持代码功能不变。

【原始代码】：
\\`\\`\\`python
{code}
\\`\\`\\`

要求：
1. 为模块添加顶部的文档字符串（如果合适）
2. 为每个函数添加完整的文档字符串
3. 为每个类及其方法添加文档字符串
4. 输出添加了文档的完整代码（使用 \\`\\`\\`python 代码块）
5. 不要输出解释性自然语言。
"""


def optimize_prompt(code: str, exec_summary: str) -> str:
    """
    单文件优化版（兼容旧 refine_step 调用）
    """
    return f"""
下面是一段 Python 代码和它的执行结果，请你在保证语义不变的前提下进行优化。

【原始代码】：
\\`\\`\\`python
{code}
\\`\\`\\`

【执行结果】：
{exec_summary}

要求：
1. 在保证语义不变的前提下优化代码
2. 输出优化后的完整代码（使用 \\`\\`\\`python 代码块）
3. 不要输出解释性自然语言。
"""


# =========================================================
# ⭐ v2.8：多文件优化 + 自动生成测试文件（v3.0 主力）
# =========================================================

def optimize_prompt_v28(all_code_context: str, exec_summary: str) -> str:
    """
    v2.8/v3.0：多文件优化 + 自动生成测试文件（支持 FileOps Parser 3.0）
    """
    return f"""
你是一名专业的软件工程师，负责优化一个多文件 Python 项目，并自动生成测试。

下面是项目的全部文件内容（由 # FILE: 标记）：
============================================================
{all_code_context}
============================================================

下面是执行结果（stdout / stderr / error）：
============================================================
{exec_summary}
============================================================

你的任务：
1. 分析整个项目结构（不是单个文件）
2. 根据执行结果修复错误
3. 优化代码结构、命名、可读性、健壮性
4. 自动生成 pytest 测试文件（tests/test_xxx.py）
5. 测试文件必须覆盖：
   - 正常情况
   - 边界情况（空列表、单元素、重复元素）
   - 异常情况（非法输入、不支持的算法）
6. 如需修改多个文件，请使用 v3.0 协议输出：

# FILE: path/to/file.py
<文件内容>

# TEST: tests/test_xxx.py
<测试内容>

# DOC: docs/README.md
<文档内容>

7. 测试文件必须放在 tests/ 目录下。

8. 关于 # META: 和 # DEPENDS: 的严格要求（必须遵守）：
   - # META: 后面必须紧跟纯 JSON 对象，不能有任何其他文本
   - # DEPENDS: 后面必须紧跟纯 JSON 对象，不能有任何其他文本
   - JSON 必须在同一行或紧接的下一行，不能有代码块标记
   - 示例格式：
     # META:
     {{"version": "1.0", "author": "AlphaPilot"}}
     
     # DEPENDS:
     {{"requirements": ["numpy>=1.20"]}}

   - 如果不确定是否需要 META/DEPENDS，可以省略这两个指令

只输出多文件协议内容，不要任何解释性文字。
"""
