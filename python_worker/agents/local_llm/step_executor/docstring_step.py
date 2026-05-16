# -*- coding: utf-8 -*-
# step_executor/docstring_step.py
# ---------------------------------------------------------
# Local LLM 代码注释步骤执行器
# - 为代码生成完整的 docstring
# - 符合 AlphaPilot 多文件协议
# ---------------------------------------------------------

from ..local_api import call_local_llm
from ..personas import PERSONA_CONFIGS


def run_docstring_step(prompt: str, context: dict, api_func=None, task_id: str = None) -> dict:
    """
    为代码生成完整的 docstring
    
    参数:
        prompt: 提示词
        context: 上下文对象
        api_func: 可选的自定义 API 函数
        task_id: 任务 ID
    
    返回:
        dict: 步骤执行结果
    """
    # 使用工程师人格配置
    persona_config = PERSONA_CONFIGS.get("engineer", PERSONA_CONFIGS["engineer"])
    
    system_prompt = persona_config["system_prompt"]
    
    # 构建完整的提示词
    full_prompt = f"""{system_prompt}

任务：为以下代码生成完整的 docstring（多文件协议）

要求：
1. 使用 `# FILE:` 开头标识每个文件
2. 为每个函数/类添加完整的 docstring
3. 包含参数说明、返回值说明、异常说明
4. 遵循 PEP 257 规范
5. 不得省略任何函数或类

代码：
{prompt}

请生成完整的注释代码。
"""
    
    try:
        # 调用 API
        if api_func:
            result = api_func(full_prompt)
        else:
            result = call_local_llm(full_prompt, task_id=task_id)
        
        return {
            "text": result,
            "success": True
        }
    
    except Exception as e:
        return {
            "text": f"docstring：LLM 调用失败：{str(e)}",
            "success": False,
            "error": str(e)
        }
