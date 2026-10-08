# -*- coding: utf-8 -*-
# step_executor/prompts.py
# ---------------------------------------------------------
# 所有步骤类型的 prompt 模板（v3.0 执行链版）
# ---------------------------------------------------------

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
]


def analyze_prompt(user_input: str) -> str:
    return f"""
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
6. 若任务会修改代码，最后给出一条建议执行的测试命令，单独写成 `TEST_COMMAND: <完整命令>`；只提出命令，绝不执行。命令应使用项目已有的测试工具，不得包含命令链、管道或重定向。

请使用自然语言描述，不要生成完整代码。
"""


def mentor_plan_prompt(analysis: str) -> str:
    return f"""
根据下面的项目分析，为用户制定针对当前项目的人工测试流程。只提供说明，不生成代码、不运行命令、不修改文件。

【项目分析】：
{analysis}

请按以下标题输出：
1. 启动方式
2. 测试入口
3. 操作步骤
4. 预期结果
5. 失败判断

只陈述分析中有证据支持的项目事实。资料未提供的内容请明确标注“未从当前项目资料确认”，不要猜测。
"""


def write_prompt(plan: str, user_request: str = "") -> str:
    """
    write 步骤的 prompt：根据规划生成代码（多文件协议 v3.0）
    包含用户原始请求以保持上下文连贯
    """
    user_section = ""
    if user_request:
        user_section = f"""
====================
【用户的原始请求 — 这是你最需要满足的目标】：
{user_request}

"""
    
    return f"""你现在处于 AlphaPilot OS v3.0 环境。

请严格按照以下"多文件输出协议"生成结果：

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
{{"requirements": ["dependency>=version"]}}

# DELETE: <用户明确指定的工作区相对路径>
==========================
{user_section}
【代码规划】：
{plan}

⭐⭐⭐ 强制要求（必须遵守）：

1. 必须使用 "# FILE:" 开头声明文件路径  
   - 格式：# FILE: path/to/file.py
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

6. 代码完整性（最高优先级）：
   - 每个函数必须有完整的、可运行的实际实现
   - 严禁使用 pass、...、raise NotImplementedError 作为函数体
   - 即使是最简单的工具函数也要给出实际逻辑
   - 如果确实无法确定实现细节，给出最合理的实现并添加注释

7. 代码质量要求：
   - 代码必须可运行
   - 变量命名清晰
   - 逻辑结构与规划一致
   - 包含必要的注释和文档字符串

8. 删除任务规则：
   - 仅当用户明确要求删除且提供了明确相对路径时，才为每个目标输出一行 "# DELETE: 相对路径"
   - DELETE 行不跟随文件内容；不得输出 shell 命令、代码删除逻辑或其他文件操作
   - 路径不明确时不要猜测，要求用户澄清

【常见任务示例】

示例1 — 用户要求"生成 requirements.txt"：
# FILE: requirements.txt
fastapi>=0.100.0
uvicorn>=0.23.0
numpy>=1.20.0
pydantic>=2.0.0
pytest>=7.0.0

示例2 — 用户要求"安装依赖"：
你应在分析步中识别出需要安装的包，在 write 步中生成安装所需的配置或脚本文件。
不要生成空的 pass 函数。

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


def fix_prompt(path: str, code: str, error_message: str, test_code: str = "") -> str:
    """
    生成自动修复代码的 prompt

    参数:
        path: 文件路径
        code: 原始代码字符串
        error_message: 执行错误信息
        test_code: 测试代码（可选，用于测试驱动修复）

    返回:
        str: 用于调用 LLM 的完整 prompt
    """
    base_prompt = f"""
下面是一段代码和它的执行错误，请分析错误原因并给出修复后的完整代码。

文件路径：{path}

【原始代码】：
```python
{code}
```

【执行错误】：
{error_message}
"""

    # ⭐ 新增：如果有测试代码，添加到 prompt 中
    if test_code:
        base_prompt += f"""

【测试代码】（你的修复必须通过以下测试）：
```python
{test_code}
```

⚠️ 重要提示：
- 测试代码定义了接口期望（方法名、参数签名、返回值类型）
- 请确保修复后的代码与测试代码中的调用方式完全匹配
- 如果测试使用了特定的 fixture 或 mock，请参考其使用方式
"""

    base_prompt += """

要求：
1. 分析错误的根本原因
2. 给出修复后的完整代码（使用 ```python 代码块）
3. 简要说明修复了什么问题（可以用注释形式写在代码里）
4. 不要输出解释性自然语言。
"""

    return base_prompt


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