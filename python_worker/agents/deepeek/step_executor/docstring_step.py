# -*- coding: utf-8 -*-
# step_executor/docstring_step.py
# ---------------------------------------------------------
# DeepSeek Worker v3.0 - 独立 docstring 步骤
# - 优先使用 write_step 的 file_ops（最稳定）
# - 为每个 Python 文件自动生成 docstring
# - 支持 # FILE: 协议输出
# - 支持流式输出
# ---------------------------------------------------------

from .utils import extract_code
from .prompts import docstring_prompt
from ....file_ops import filter_valid_file_ops, get_python_files
from ....worker_config import stream_start, stream_end
from ..deepseek_api import call_deepseek


def run_docstring_step(step, context, events, task_id=None):
    """
    v3.0 docstring 步骤（DeepSeek 版本）
    - 使用 filter_valid_file_ops() 过滤内部元数据
    - 使用 get_python_files() 提取 Python 文件
    - 为每个 Python 文件生成 docstring
    """

    if task_id:
        stream_start(task_id, "📝 正在为代码添加 docstring...", phase="docstring")

    # ===== 1. 获取 file_ops（关键：优先使用 final_file_ops）=====
    file_ops = (
        context.get("final_file_ops") or  # ⭐ 唯一真相源
        context.get("file_ops") or
        []
    )

    if not file_ops:
        step["output"] = {"text": "docstring：未找到可处理的文件。"}
        return

    # ⭐ v3.0 修复：使用工具函数过滤有效 FileOps
    valid_file_ops = filter_valid_file_ops(file_ops)

    if not valid_file_ops:
        step["output"] = {"text": "docstring：未找到可处理的文件。"}
        return

    # ⭐ 使用便捷函数提取 Python 文件
    py_files = get_python_files(file_ops)

    if not py_files:
        step["output"] = {"text": "docstring：没有可处理的 Python 文件。"}
        return

    # ===== 2. 为每个 Python 文件生成 docstring =====
    results = []
    
    for fo in py_files:
        path = fo["path"]
        content = fo.get("content", "")
        
        if not content:
            continue
        
        try:
            prompt = docstring_prompt(content)
            
            # 调用 DeepSeek API
            response = call_deepseek(prompt, stream=False)
            
            documented_code = extract_code(response, fallback_strategies=True)
            
            if documented_code:
                results.append({
                    "path": path,
                    "original": content,
                    "documented": documented_code
                })
                
        except Exception as e:
            print(f"[ERROR] 处理 {path} 时出错: {e}")
            results.append({
                "path": path,
                "original": content,
                "documented": content,
                "error": str(e)
            })

    # ===== 3. 构建输出 =====
    if results:
        output_text = f"✅ 已为 {len(results)} 个 Python 文件生成 docstring\n\n"
        for r in results:
            output_text += f"- {r['path']}\n"
        
        step["output"] = {
            "text": output_text,
            "documented_files": results
        }
    else:
        step["output"] = {"text": "docstring：未能生成任何 docstring。"}

    if task_id:
        stream_end(task_id)
