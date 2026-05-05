# -*- coding: utf-8 -*-
# step_executor/prompts.py
# ---------------------------------------------------------
# 所有步骤类型的 prompt 模板
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
]


def analyze_prompt(user_input: str) -> str:
    """
    analyze 步骤的 prompt：分析用户需求
    
    参数:
        user_input: 用户输入的自然语言任务描述
    
    返回:
        str: 用于调用 LLM 的完整 prompt
    """
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
    """
    plan 步骤的 prompt：根据分析结果生成代码结构规划
    
    参数:
        analysis: analyze 步骤的分析结果
    
    返回:
        str: 用于调用 LLM 的完整 prompt
    """
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
    write 步骤的 prompt：根据规划生成代码
    
    参数:
        plan: plan 步骤的规划内容
    
    返回:
        str: 用于调用 LLM 的完整 prompt
    """
    return f"""
请根据下面的代码规划生成完整的 Python 代码：

【代码规划】：
{plan}

要求：
1. 输出完整的 Python 代码（保持 ```python 格式）
2. 代码必须可运行
3. 变量命名清晰
4. 逻辑结构与规划一致
5. 不要包含解释性文字，只输出代码
6. 输出必须是合法 Python 代码，不要包含解释性文字
"""


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
6. 输出必须是合法 Markdown 文档，不要包含解释性文字
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
