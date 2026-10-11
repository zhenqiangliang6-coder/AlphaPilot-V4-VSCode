# -*- coding: utf-8 -*-
# fix_step_v3.py — 统一函数签名 + 支持多文件协议 + 不执行代码

from .utils import extract_code
from .prompts import fix_prompt
from ....file_ops import parse_fileops_v3, create_file_op
from ....worker_config import stream_start, stream_chunk, stream_end
from ..modelscope_api import call_modelscope


def _get_test_context(context):
    """
    从 context 中提取测试代码和错误信息
    
    参数:
        context: 执行上下文
    
    返回:
        (error_info, test_code): 错误信息和测试代码
    """
    error_info = ""
    test_code = ""
    
    # 从 intermediate_results 中提取
    for item in context.get("intermediate_results", []):
        if item.get("type") == "test":
            # 提取错误信息
            error = item.get("error", "")
            if error:
                error_info = error
            # 提取测试代码
            tc = item.get("test_code", "")
            if tc:
                test_code = tc
            break
    
    # 如果没有找到测试代码，尝试从其他来源提取
    if not error_info:
        error_info = context.get("last_error", "")
    
    return error_info, test_code


def run_fix_step(
    step, 
    context, 
    events, 
    task_id=None,
    llm_client=None,  # ⭐ 依赖注入：LLM 客户端
    file_parser=None,  # ⭐ 依赖注入：文件解析器
    python_compiler=None  # ⭐ 依赖注入：Python 编译器
):
    """
    v3.0 修复步骤（不执行代码，只生成 file_ops）
    """

    # ===== 流式输出开始 =====
    if task_id:
        stream_start(task_id, "🔧 正在根据错误信息修复代码...", phase="fix")

    # ===== 获取错误信息和测试代码 =====
    error_info, test_code = _get_test_context(context)

    # ===== 获取源文件 =====
    source_files = context.get("meta", {}).get("source_files", {})
    
    if not source_files:
        # 尝试从 final_file_ops 提取
        final_file_ops = context.get("final_file_ops", [])
        if final_file_ops:
            source_files = {op.get("path", ""): op.get("content", "") for op in final_file_ops}

    if not source_files:
        step["output"] = {
            "text": "fix：未找到可修复的源代码。",
            "file_ops": [],
        }
        if task_id:
            stream_end(task_id)
        return

    file_ops = []
    errors = []
    
    for path, original_code in source_files.items():
        # ⭐ 将测试代码传递给 fix_prompt
        prompt = fix_prompt(path, original_code, error_info, test_code)
        
        try:
            # ⭐ 依赖注入：使用注入的 LLM 客户端，或默认使用真实实现
            if llm_client is not None:
                response = llm_client.call(prompt)
            else:
                response = call_modelscope(prompt)
            
            # ⭐ 依赖注入：使用注入的文件解析器，或默认使用真实实现
            if file_parser is not None:
                parsed_ops = file_parser.parse(response)
            else:
                parsed_ops = parse_fileops_v3(response)
            
            # ⭐ 依赖注入：使用注入的 Python 编译器进行语法检查
            if python_compiler is not None:
                for op in parsed_ops:
                    content = op.get("content", "")
                    if content:
                        try:
                            python_compiler.compile(content, path, mode="exec")
                        except SyntaxError as e:
                            errors.append(f"Syntax error in {path}: {e}")
                            continue
            else:
                # 使用默认 compile
                for op in parsed_ops:
                    content = op.get("content", "")
                    if content:
                        try:
                            compile(content, path, mode="exec")
                        except SyntaxError as e:
                            errors.append(f"Syntax error in {path}: {e}")
                            continue
            
            file_ops.extend(parsed_ops)
            
        except Exception as e:
            errors.append(f"Error processing {path}: {str(e)}")

    # ===== 写入输出 =====
    step["output"] = {
        "text": "修复完成" + (f"\n{errors}" if errors else ""),
        "file_ops": file_ops,
    }

    # ===== 写入上下文 =====
    context["file_ops"] = file_ops
    context["intermediate_results"].append({
        "type": "fix",
        "file_ops": file_ops
    })

    # ===== 流式输出结束 =====
    if task_id:
        stream_end(task_id)
