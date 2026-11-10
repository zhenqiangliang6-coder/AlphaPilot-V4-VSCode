# -*- coding: utf-8 -*-
# refine_step_v3.py — v3.5 工业级多语言版

from ....file_ops import (
    parse_fileops_v3,
    filter_valid_file_ops,
    get_code_files,
    merge_file_ops,
)
from ....worker_config import stream_start, stream_chunk, stream_end
from ..qwen_api import call_qwen_with_persona, call_llm, call_llm_with_persona


def run_refine_step(step, context, events, task_id=None):
    """
    v3.5 refine step（工业级 + 多语言）
    - 使用 get_code_files() 提取所有语言代码文件（不再是 .py only）
    - 使用 merge_file_ops() 增量合并，保护非目标文件不被丢弃
    - 使用 # FILE: 协议构建 LLM prompt，支持全语言
    - 如果模型没有生成新的 file_ops，则保留原始 file_ops
    """

    if task_id:
        stream_start(task_id, "🔧 正在优化代码...", phase="refine")

    file_ops = context.get("file_ops", [])

    # v3.5: 使用 get_code_files() 提取所有受支持语言的代码文件
    code_files = get_code_files(file_ops)
    valid_file_ops = filter_valid_file_ops(file_ops)

    if not code_files:
        # 降级：没有匹配的代码文件，直接返回
        step["output"] = {
            "text": "refine 完成（无代码文件需要优化）",
            "file_ops": context.get("final_file_ops", [])
        }
        if task_id:
            stream_end(task_id)
        return

    # v3.5: 构建 # FILE: 协议项目，支持所有语言
    language_counts = {}
    virtual_project_parts = []
    for fo in code_files:
        path = fo["path"]
        content = fo.get("content", "")
        _count_file_language(path, language_counts)
        virtual_project_parts.append(f"# FILE: {path}\n{content}\n")

    virtual_project = "".join(virtual_project_parts)
    lang_summary = ", ".join(f"{lang}({n})" for lang, n in sorted(language_counts.items()))

    prompt = f"请优化以下项目代码（包含 {lang_summary}）：\n\n{virtual_project}"

    meta = context.get("meta", {})
    persona = meta.get("persona_config")

    if persona:
        response = call_llm_with_persona(prompt, persona, use_stream=False)
    else:
        response = call_llm(prompt)

    # 解析模型输出
    refined_file_ops = parse_fileops_v3(response)

    # v3.5: 使用 merge_file_ops 增量合并（保护非代码文件不被丢弃）
    if refined_file_ops:
        merge_file_ops(context, refined_file_ops, source_step="refine")
    else:
        # 保持原有 file_ops 不变
        pass

    step["output"] = {
        "text": f"refine 完成（处理 {lang_summary}）",
        "file_ops": context.get("final_file_ops", [])
    }

    if task_id:
        stream_end(task_id)


def _count_file_language(file_path: str, counter: dict) -> None:
    """
    v3.5: 按扩展名统计语言分布，用于日志摘要
    """
    if not file_path:
        return
    for ext in (".tsx", ".ts", ".jsx", ".mjs", ".cjs", ".js",
                ".py", ".pyi", ".java", ".go", ".rs", ".rb",
                ".php", ".cpp", ".c", ".h", ".cs", ".swift",
                ".kt", ".scala", ".vue", ".svelte", ".dart",
                ".sh", ".sql", ".ex", ".erl", ".hs", ".clj"):
        if file_path.endswith(ext):
            counter[ext] = counter.get(ext, 0) + 1
            return
    counter["other"] = counter.get("other", 0) + 1