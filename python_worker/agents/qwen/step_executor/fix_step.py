# -*- coding: utf-8 -*-
# fix_step_v3.py — 统一函数签名 + 支持多文件协议 + 不执行代码

from .utils import extract_code
from .prompts import fix_prompt
from ....file_ops import parse_fileops_v3, create_file_op
from ....worker_config import stream_start, stream_chunk, stream_end
from ..qwen_api import call_qwen_with_persona, call_qwen


def run_fix_step(step, context, events, task_id=None):
    """
    v3.0 修复步骤（不执行代码，只生成 file_ops）
    """

    # ===== 流式输出开始 =====
    if task_id:
        stream_start(task_id, "🔧 正在根据错误信息修复代码...", phase="fix")

    # ===== 获取错误信息和原始代码 =====
    error_info = context.get("last_error", "")
    original_code = context.get("last_code", "")

    # ===== 构造 prompt =====
    prompt = fix_prompt(original_code, error_info)

    # ===== 调用模型 =====
    meta = context.get("meta", {})
    persona = meta.get("persona_config")

    if persona:
        response = call_qwen_with_persona(prompt, persona, use_stream=False)
    else:
        response = call_qwen(prompt)

    # ===== 提取代码 =====
    fixed_code = extract_code(response, fallback_strategies=True)

    # ===== 解析 file_ops =====
    file_ops = parse_fileops_v3(response)

    # ===== 写入输出 =====
    step["output"] = {
        "text": "修复完成",
        "file_ops": file_ops,
        "fixed_code": fixed_code
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
