# -*- coding: utf-8 -*-
# step_executor/prompts.py — AlphaPilot OS v3.0（对齐现有代码版）
# ---------------------------------------------------------

__all__ = [
    "analyze_prompt",
    "plan_prompt",
    "write_prompt",
    "optimize_prompt",
    "test_prompt",
    "fix_prompt",
    "profile_prompt",
    "doc_prompt",
    "docstring_prompt",
]

def analyze_prompt(user_input: str) -> str:
    return f"""
你是 AlphaPilot OS 的 analyze 模块。

请分析用户任务描述，输出结构化分析：

【输出格式】
- 任务目标：
- 输入：
- 输出：
- 关键功能点：
- 难点：
- 可能的模块结构：

用户输入：
{user_input}
"""

def plan_prompt(analysis: str) -> str:
    return f"""
你是 AlphaPilot OS 的 plan 模块。

根据 analyze 的分析内容，生成项目规划：

【输出格式】
# 项目规划
1. 模块结构（文件列表）
2. 每个文件的职责
3. 关键函数设计
4. 数据结构
5. 伪代码（必须包含）

分析内容：
{analysis}
"""

def write_prompt(plan: str) -> str:
    return f"""
你是 AlphaPilot OS 的 write 模块。

根据项目规划，生成完整项目代码，使用多文件协议 v3.0：

【多文件协议 v3.0 - 严格格式】
# FILE: path/to/file.py
直接写代码内容，不要任何标签或标记

# TEST: tests/test_xxx.py
直接写测试代码

# DOC: docs/xxx.md
直接写文档内容

# META:
{{ "any": "metadata" }}

# DEPENDS:
{{ "deps": [] }}

【重要要求】
1. ❌ 禁止使用 <代码>、</代码>、<内容>、```python 等任何标签或代码块标记
2. ✅ # FILE: 后面直接换行，然后就是纯代码内容
3. ✅ 每个文件之间用空行分隔
4. ✅ 必须至少生成 1 个 FILE
5. ✅ 代码必须可运行
6. ✅ 不要解释，不要多余文字
7. ✅ 只输出多文件协议内容

【正确示例】
# FILE: hello.py
def greet():
    return "Hello"

# FILE: main.py
from hello import greet
print(greet())

【错误示例 - 禁止这样输出】
# FILE: hello.py
<代码>
def greet():
    return "Hello"
</代码>

项目规划：
{plan}
"""

def optimize_prompt(code: str, exec_summary: str) -> str:
    return f"""
你是 AlphaPilot OS 的 refine 模块。

下面是一段（可能是多文件协议中的）Python 代码及其执行结果，请在保持语义不变的前提下进行优化。

【原始代码或多文件片段】：
{code}

【执行结果】：
{exec_summary}

【优化要求】
1. 修复潜在 bug
2. 优化结构
3. 提升可读性
4. 保持功能一致
5. ❌ 禁止使用 <代码>、</代码>、```python 等任何标签
6. ✅ 如果输入是多文件协议，则输出必须使用多文件协议 v3.0（# FILE: 直接跟代码）
7. ✅ 如果输入是单文件代码，则直接输出纯代码（无标签）
8. ✅ 不要解释，不要多余文字

【正确示例 - 多文件协议】
# FILE: hello.py
def greet():
    return "Hello"

【错误示例 - 禁止这样输出】
# FILE: hello.py
<代码>
def greet():
    return "Hello"
</代码>
"""

def test_prompt(code: str) -> str:
    return f"""
你是 AlphaPilot OS 的 test 模块。

请为下面的 Python 代码生成 pytest 风格测试：

【要求】
- 使用 assert
- 覆盖正常情况、边界情况、异常情况
- 不要 import pytest（Worker 会自动注入 fake pytest）
- 不要解释，只输出 \\`\\`\\`python 代码块

代码：
\\`\\`\\`python
{code}
\\`\\`\\`
"""

def fix_prompt(code: str, error_message: str) -> str:
    return f"""
你是 AlphaPilot OS 的 fix 模块。

下面是一段 Python 代码及其执行错误，请分析错误原因并给出修复后的完整代码。

【原始代码或多文件片段】：
{code}

【执行错误】：
{error_message}

【要求】
1. 分析错误的根本原因
2. 给出修复后的完整代码
3. ❌ 禁止使用 <代码>、</代码>、```python 等任何标签
4. ✅ 如果输入是多文件协议，则输出必须使用多文件协议 v3.0（# FILE: 直接跟代码）
5. ✅ 如果输入是单文件代码，则直接输出纯代码（无标签）
6. ✅ 不要解释，不要多余文字

【正确示例 - 多文件协议】
# FILE: hello.py
def greet():
    return "Hello"

【错误示例 - 禁止这样输出】
# FILE: hello.py
<代码>
def greet():
    return "Hello"
</代码>
"""

def profile_prompt(code: str) -> str:
    return f"""
你是 AlphaPilot OS 的 profile 模块。

请对下面的代码（可能是单文件，也可能是多文件协议中的某个文件）进行性能分析：

【代码】：
{code}

请分析：
- 时间复杂度（大 O 表示法）
- 空间复杂度
- 性能瓶颈在哪里
- 如何优化（给出具体的优化建议）
"""

def doc_prompt(code: str) -> str:
    return f"""
你是 AlphaPilot OS 的 doc 模块。

请为下面的 code（可以是整个项目的多文件协议）生成 README 风格的 Markdown 文档：

【代码或多文件协议】：
{code}

请生成：
- 项目简介
- 功能列表
- 文件结构（如果是多文件）
- 使用方法
- 示例
- 注意事项

输出合法 Markdown，不要解释，不要多余文字。
"""

def docstring_prompt(code: str) -> str:
    return f"""
你是 AlphaPilot OS 的 docstring 模块。

请在下面这段 code中添加完整的文档字符串（docstring），保持 code功能不变。

【原始代码或多文件片段】：
{code}

【要求】
- 为模块添加顶部 docstring（如果合适）
- 为每个函数添加 docstring（参数、返回值、异常）
- 为每个类及其方法添加 docstring
- 输出完整 code，使用 \\`\\`\\`python 代码块
- 不要解释，不要多余文字。
"""
