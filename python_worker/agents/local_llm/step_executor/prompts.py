
# -*- coding: utf-8 -*-
# step_executor/prompts.py
# ---------------------------------------------------------
# 所有步骤类型的 prompt 模板（本地 LLM + 多文件协议版）
# ---------------------------------------------------------

__all__ = [
    "analyze_prompt",
    "plan_prompt",
    "write_prompt",
    "refine_prompt",
    "test_prompt",
    "fix_prompt",
    "profile_prompt",
    "doc_prompt",
    "docstring_prompt",
    "optimize_prompt",
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

请使用自然语言描述，不要生成完整代码。
"""


def write_prompt(plan: str) -> str:
    """
    Multi‑File Protocol v3.2 — 对齐 persona system_prompt 的 ### 格式
    
    ⭐ v3.2.2 修复版：统一使用 ### 分隔符格式,避免与 persona system_prompt 冲突
    ⭐ v3.2.3 新增：要求 Gemma 4B 输出 ASCII 文件树（无需前端改动）
    """
    return f"""你现在处于 AlphaPilot OS v3.2 环境。

请严格按照以下"多文件输出协议"生成代码：

==========================
### <relative path>
<代码内容>

### <测试文件路径>
<测试代码内容>

### <文档路径>
<文档内容>

### FILE_TREE
<ASCII 文件树结构>
==========================

【代码规划】：
{plan}

**重要提醒**:
1. 必须使用 `###` 作为文件分隔符
2. 不要输出任何解释、思考过程或元描述
3. 直接输出代码文件内容
4. 每个文件以 `### 文件名` 开头
5. **必须在最后输出 ASCII 文件树**（使用 ### FILE_TREE 分隔符）

**ASCII 文件树格式示例**:
```
### FILE_TREE
project/
├── calculator.py
├── tests/
│   ── test_calculator.py
└── README.md
```

**文件树规则**:
- 使用 ├─ 和 └─ 符号表示层级关系
- 文件夹后面加 /
- 缩进使用 4 个空格
- 只展示生成的文件，不要展示无关文件

现在 please directly output code file:"""


def refine_prompt(code: str, exec_summary: str) -> str:
    """
    refine 步骤的 prompt：根据执行结果优化代码
    
    参数:
        code: 原始代码
        exec_summary: 执行结果摘要（stdout/stderr/error）
    
    返回:
        str: 用于调用 LLM 的完整 prompt
    """
    return f"""
下面是一段 Python 代码及其执行结果，请在保持语义不变的前提下优化代码：

【原始代码】：
```python
{code}
```

【执行结果】：
{exec_summary}

要求：
1. 在保证语义不变的前提下优化代码
2. 输出优化后的完整代码（保持 ```python 格式）
3. 输出必须是合法 Python 代码，不要包含解释性文字
"""


def test_prompt(code: str) -> str:
    """
    生成 pytest 风格单元测试的 prompt
    
    参数:
        code: 被测代码字符串
    
    返回:
        str: 用于调用 LLM 的完整 prompt
    """
    return f"""
下面是一段 Python 代码，请你为它生成 pytest 风格的单元测试代码。

【被测试代码】：
```python
{code}
```

要求：
1. 使用 pytest 风格（assert + pytest.raises）
2. 不要 import pytest（Worker 会自动注入 fake pytest）
3. 覆盖正常情况、边界情况、异常情况
4. 包含清晰的断言
5. 输出完整的测试代码（保持 ```python 格式）
6. 输出必须是合法 Python 代码，不要包含解释性文字
"""


def fix_prompt(code: str, error_message: str) -> str:
    """
    生成自动修复代码的 prompt
    
    参数:
        code: 原始代码字符串
        error_message: 执行错误信息
    
    返回:
        str: 用于调用 LLM 的完整 prompt
    """
    return f"""
下面是一段 Python 代码和它的执行错误，请分析错误原因并给出修复后的完整代码：

【原始代码】：
```python
{code}
```

【执行错误】：
{error_message}

要求：
1. 分析错误的根本原因
2. 给出修复后的完整代码（保持 ```python 格式）
3. 简要说明修复了什么问题
4. 输出必须是合法 Python 代码，不要包含解释性文字
"""


def profile_prompt(code: str) -> str:
    """
    生成性能分析的 prompt
    
    参数:
        code: 待分析的代码字符串
    
    返回:
        str: 用于调用 LLM 的完整 prompt
    """
    return f"""
请对下面的 Python 代码进行性能分析：

【代码】：
```python
{code}
```

请分析：
1. 时间复杂度（大 O 表示法）
2. 空间复杂度
3. 性能瓶颈在哪里
4. 如何优化（给出具体的优化建议）
5. 如果可能，提供优化后的代码示例
6. 输出必须是合法 Python 代码，不要包含解释性文字
"""


def doc_prompt(code: str) -> str:
    """
    生成完整文档的 prompt
    
    参数:
        code: 需要生成文档的代码字符串
    
    返回:
        str: 用于调用 LLM 的完整 prompt
    """
    return f"""
请为下面的 Python 代码生成完整的文档：

【代码】：
```python
{code}
```

请生成：
1. 模块级别的文档字符串（说明用途、功能）
2. 每个函数的完整文档（参数说明、返回值、异常、示例）
3. 类的文档（如果有类）
4. 使用示例代码
5. 注意事项
6. 输出必须是合法 Python 代码，不要包含解释性文字
"""


def docstring_prompt(code: str) -> str:
    """
    为代码添加 docstring 的 prompt
    
    参数:
        code: 需要添加文档字符串的代码
    
    返回:
        str: 用于调用 LLM 的完整 prompt
    """
    return f"""
请在下面这段 Python 代码中添加完整的文档字符串（docstring），保持代码功能不变：

【原始代码】：
```python
{code}
```

要求：
1. 为模块添加顶部的文档字符串
2. 为每个函数添加完整的文档字符串（包括参数、返回值、示例）
3. 输出添加了文档的完整代码（保持 ```python 格式）
4. 输出必须是合法 Python 代码，不要包含解释性文字
"""


def optimize_prompt(code: str, exec_summary: str) -> str:
    """
    生成代码优化的 prompt
    
    参数:
        code: 原始代码字符串
        exec_summary: 执行结果摘要
    
    返回:
        str: 用于调用 LLM 的完整 prompt
    """
    return f"""
下面是一段 Python 代码和它的执行结果，请你在保证语义不变的前提下进行优化：

【原始代码】：
```python
{code}
```

【执行结果】：
{exec_summary}

要求：
1. 在保证语义不变的前提下优化代码
2. 输出优化后的完整代码（保持 ```python 格式）
3. 输出必须是合法 Python 代码，不要包含解释性文字
"""
