# -*- coding: utf-8 -*-
# refine_step_v3.py — 统一函数签名 + 支持多文件协议 + 不执行代码

from .utils import extract_code
from .prompts import fix_prompt
from ....file_ops import parse_fileops_v3, create_file_op
from ....worker_config import stream_start, stream_chunk, stream_end
from ..modelscope_api import call_modelscope


def run_refine_step(step, context, events, task_id=None):
    """
    v3.0 修复步骤（不执行代码，只生成 file_ops）
    """

    # ===== 流式输出开始 =====
    if task_id:
        stream_start(task_id, "🔧 正在优化代码...", phase="refine")

    file_ops = context.get("file_ops", [])

    # ⭐ v3.1.1 修复：使用工具函数过滤有效 FileOps
    from ....file_ops import filter_valid_file_ops
    valid_file_ops = filter_valid_file_ops(file_ops)

    # 构建虚拟项目
    virtual_project = ""
    for fo in valid_file_ops:
        if fo["path"].endswith(".py"):
            virtual_project += f"# FILE: {fo['path']}\n{fo['content']}\n\n"

    prompt = f"请优化以下 Python 项目代码：\n\n{virtual_project}"

    meta = context.get("meta", {})
    persona = meta.get("persona_config")

    if persona:
        response = call_modelscope(prompt)
    else:
        response = call_modelscope(prompt)

    # 解析模型输出
    refined_file_ops = parse_fileops_v3(response)

    # ⭐ 方向 A：如果模型没有生成新的 file_ops，则保留原始 file_ops
    if refined_file_ops:
        # ⭐ 更新 final_file_ops（唯一真相源）
        context["final_file_ops"] = refined_file_ops
        context["file_ops"] = refined_file_ops
    else:
        # 保持原有 file_ops 不变
        pass

    step["output"] = {
        "text": "refine 完成",
        "file_ops": context.get("final_file_ops", [])
    }

    if task_id:
        stream_end(task_id)
