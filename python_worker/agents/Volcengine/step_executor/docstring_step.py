# -*- coding: utf-8 -*-
# step_executor/docstring_step.py
# ---------------------------------------------------------
# Doubao Worker v3.0 - 独立 docstring 步骤（流式输出 + 人格配置版）
# - 优先使用 write_step 的 file_ops（最稳定）
# - 为每个 Python 文件自动生成 docstring
# - 支持 # FILE: 协议输出
# - 支持流式输出
# ⭐ 支持人格配置（从 context.meta 读取）
# ---------------------------------------------------------

from .utils import extract_code
from .prompts import docstring_prompt
from ....file_ops import filter_valid_file_ops, get_python_files
from ....worker_config import stream_start, stream_end, stream_chunk
from ..doubao_api import call_doubao, call_doubao_stream


def run_docstring_step(step, context, events, task_id=None):
    """
    v3.0 docstring 步骤（Doubao 版本 + 流式输出 + 人格配置）
    - 使用 filter_valid_file_ops() 过滤内部元数据
    - 使用 get_python_files() 提取 Python 文件
    - 为每个 Python 文件生成 docstring
    
    ⭐ 流式输出支持：
        - 通过 task_id 发送 stream_chunk 事件
        - 实时展示 AI 文档字符串生成过程 (channel=content)
    
    ⭐ 人格配置支持：
        - 从 context.meta 读取 persona 类型
        - 动态注入 System Prompt
    
    参数:
        step: 步骤对象
        context: 上下文对象
        events: 事件列表
        task_id: 任务 ID（用于流式输出）
    """

    # ===== 第0层：启动流式输出 =====
    if task_id:
        try:
            stream_start(task_id, "📝 正在为代码添加 docstring...", phase="docstring")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # ===== 第0.5层：⭐ 获取人格配置（豆包独立实现）=====
    persona_config = None
    try:
        meta = context.get("meta", {})
        persona_type = meta.get("persona", "engineer")
        
        from ..personas import get_persona_config
        persona_config = get_persona_config(persona_type)
        
        print(f"🎨 docstring_step 使用人格: {persona_config['name']}")
    except Exception as e:
        print(f"[WARN] 获取人格配置失败: {e}")
        persona_config = None

    # ===== 1. 获取 file_ops（关键：优先使用 final_file_ops）=====
    file_ops = (
        context.get("final_file_ops") or  # ⭐ 唯一真相源
        context.get("file_ops") or
        []
    )

    if not file_ops:
        msg = "docstring：未找到可处理的文件。"
        if task_id:
            stream_chunk(task_id, msg, phase="docstring", channel="reasoning")
        step["output"] = {"text": msg}
        
        if task_id:
            try:
                stream_end(task_id)
            except Exception as e:
                print(f"[WARN] stream_end 失败: {e}")
        return

    # ⭐ v3.0 修复：使用工具函数过滤有效 FileOps
    valid_file_ops = filter_valid_file_ops(file_ops)

    if not valid_file_ops:
        msg = "docstring：未找到可处理的文件。"
        if task_id:
            stream_chunk(task_id, msg, phase="docstring", channel="reasoning")
        step["output"] = {"text": msg}
        
        if task_id:
            try:
                stream_end(task_id)
            except Exception as e:
                print(f"[WARN] stream_end 失败: {e}")
        return

    # ⭐ 使用便捷函数提取 Python 文件
    py_files = get_python_files(file_ops)

    if not py_files:
        msg = "docstring：没有可处理的 Python 文件。"
        if task_id:
            stream_chunk(task_id, msg, phase="docstring", channel="reasoning")
        step["output"] = {"text": msg}
        
        if task_id:
            try:
                stream_end(task_id)
            except Exception as e:
                print(f"[WARN] stream_end 失败: {e}")
        return

    # ===== 2. 为每个 Python 文件生成 docstring（流式输出）=====
    results = []
    
    for fo in py_files:
        path = fo["path"]
        content = fo.get("content", "")
        
        if not content:
            continue
        
        try:
            # ⭐ 构建完整 prompt（含人格配置）
            if persona_config:
                system_prompt = persona_config.get("system_prompt", "")
                full_prompt = f"{system_prompt}\n\n---\n\n用户请求:\n{docstring_prompt(content)}"
            else:
                full_prompt = docstring_prompt(content)
            
            documented_code = ""
            
            # ⭐ 使用流式调用
            if task_id:
                stream_chunk(task_id, f"\n正在处理 {path}...\n", phase="docstring", channel="reasoning")
                
                for chunk in call_doubao_stream(full_prompt):
                    documented_code += chunk
                    stream_chunk(task_id, chunk, phase="docstring", channel="content")
            else:
                # 非流式模式（向后兼容）
                documented_code = call_doubao(full_prompt)
            
            documented_code = extract_code(documented_code)
            
            if documented_code:
                results.append({
                    "path": path,
                    "original": content,
                    "documented": documented_code
                })
                
        except Exception as e:
            error_msg = f"[ERROR] 处理 {path} 时出错: {e}"
            print(error_msg)
            
            if task_id:
                stream_chunk(task_id, error_msg, phase="docstring", channel="reasoning")
            
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
        msg = "docstring：未能生成任何 docstring。"
        if task_id:
            stream_chunk(task_id, msg, phase="docstring", channel="reasoning")
        step["output"] = {"text": msg}

    # ⭐ 结束流式输出
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
