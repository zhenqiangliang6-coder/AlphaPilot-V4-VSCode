# -*- coding: utf-8 -*-
# step_executor/docstring_step_v3.py
# ---------------------------------------------------------
# 独立 docstring 步骤（v3.0 稳定版）
# - 优先使用 write_step 的 file_ops（最稳定）
# - 为每个 Python 文件自动生成 docstring
# - 支持 # FILE: 协议输出
# - 支持 persona / intent
# - 支持流式输出
# ---------------------------------------------------------

import os
from .utils import extract_code
from .prompts import docstring_prompt
from ....file_ops import create_file_op, filter_valid_file_ops, get_python_files
from ....worker_config import create_event, stream_start, stream_chunk, stream_end
from ..qwen_api import call_qwen_with_persona, call_qwen


def run_docstring_step(step, context, events, task_id=None):
    """
    v3.1.1 docstring 步骤（空值保护版）
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

    # ⭐ v3.1.1 修复：使用工具函数过滤有效 FileOps
    valid_file_ops = filter_valid_file_ops(file_ops)

    if not valid_file_ops:
        step["output"] = {"text": "docstring：未找到可处理的文件。"}
        return

    # ⭐ 使用便捷函数提取 Python 文件
    py_files = get_python_files(file_ops)

    if not py_files:
        step["output"] = {"text": "docstring：没有可处理的 Python 文件。"}
        return

    # ===== 2. 获取 persona =====
    persona_config = None
    try:
        meta = context.get("meta", {})
        persona_type = meta.get("persona", "engineer")
        from ..personas import get_persona_config
        persona_config = get_persona_config(persona_type)
    except Exception as e:
        print(f"[WARN] 获取人格失败: {e}")

    # ===== 3. 为每个 Python 文件生成 docstring =====
    results = []
    
    for fo in py_files:
        path = fo["path"]
        content = fo.get("content", "")
        
        if not content:
            continue
        
        try:
            prompt = docstring_prompt(content)
            
            if persona_config:
                response = call_qwen_with_persona(prompt, persona_config, use_stream=False)
            else:
                response = call_qwen(prompt)
            
            documented_code = extract_code(response, fallback_strategies=True)
            
            if documented_code:
                compile(documented_code, path, "exec")
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

    # ===== 4. 将通过语法检查的结果回写到最终 FileOps =====
    successful_results = [result for result in results if not result.get("error")]
    documented_by_path = {result["path"]: result for result in successful_results}
    updated_file_ops = []
    matched_paths = set()

    for file_op in file_ops:
        updated_op = dict(file_op)
        result = documented_by_path.get(updated_op.get("path"))
        if result:
            updated_op["content"] = result["documented"]
            updated_op["from_step"] = "docstring"
            matched_paths.add(result["path"])
        updated_file_ops.append(updated_op)

    for result in successful_results:
        if result["path"] not in matched_paths:
            updated_file_ops.append(create_file_op(
                "modify",
                result["path"],
                result["documented"],
                reason="更新 docstring",
                from_step="docstring",
                intent=context.get("meta", {}).get("intent", ""),
            ))

    if successful_results:
        context["final_file_ops"] = updated_file_ops
        context["file_ops"] = updated_file_ops

    failed_results = [result for result in results if result.get("error")]
    if successful_results:
        output_text = f"✅ 已生成 {len(successful_results)} 个待确认的 docstring 修改\n\n"
        output_text += "\n".join(f"- {result['path']}" for result in successful_results)
        if failed_results:
            output_text += "\n\n⚠️ 以下文件未通过处理，未加入待确认修改：\n"
            output_text += "\n".join(f"- {result['path']}: {result['error']}" for result in failed_results)
        step["output"] = {"text": output_text, "documented_files": results}
    elif failed_results:
        step["output"] = {
            "text": "docstring：所有生成结果均失败或未通过 Python 语法检查，未产生文件修改。",
            "documented_files": results,
        }
    else:
        step["output"] = {"text": "docstring：未能生成任何 docstring。"}

    if task_id:
        stream_end(task_id)
