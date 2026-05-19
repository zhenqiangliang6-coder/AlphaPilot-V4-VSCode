# -*- coding: utf-8 -*-
# step_executor/refine_step.py
# ---------------------------------------------------------
# Local LLM Worker v3.2 — refine 步骤（对齐 Qwen Worker 能力）
# - ⭐ v3.2：支持多文件协议优化
# - ⭐ 与 Qwen Worker v2 完全对齐（FileOps 全链路）
# ---------------------------------------------------------

from ..local_api import call_local_llm
from .utils import extract_code, FAKE_ENVIRONMENT
from .prompts import optimize_prompt
from code_executor import run_python
from worker_config import create_event, stream_chunk, stream_start, stream_end

# ⭐ 尝试导入 file_ops，如果失败则使用空实现
try:
    import sys
    import os
    python_worker_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    if python_worker_dir not in sys.path:
        sys.path.insert(0, python_worker_dir)

    from file_ops import parse_fileops_v3, filter_valid_file_ops
    HAS_FILE_OPS = True
except ImportError as e:
    HAS_FILE_OPS = False
    print(f"[WARN] file_ops 模块不可用: {e}")

    def parse_fileops_v3(text):
        return []

    def filter_valid_file_ops(file_ops: list, exclude_internal: bool = True) -> list:
        return file_ops


def run_refine_step(step, context, events, task_id=None):
    """
    refine 步骤（v3.2）：
    - 执行 write 步骤生成的代码
    - 根据执行结果优化代码
    - ⭐ v3.2：支持多文件协议优化（对齐 Qwen Worker）
    
    参数:
        step: 步骤定义
        context: 上下文对象
        events: 事件列表
        task_id: 任务 ID（可选，用于流式输出）
    """

    # ===== 0. 流式输出开始 =====
    if task_id:
        try:
            stream_start(task_id, "⚙️ 正在执行并优化代码...", phase="refine")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # 1) ⭐ v3.2：获取当前 file_ops（唯一真相源）
    file_ops = context.get("final_file_ops", []) or context.get("file_ops", [])
    
    # ⭐ v3.2：过滤有效 FileOps
    if HAS_FILE_OPS:
        valid_file_ops = filter_valid_file_ops(file_ops)
    else:
        valid_file_ops = file_ops

    # 2) 如果没有 file_ops，回退到旧逻辑（单文件模式）
    if not valid_file_ops:
        # === 旧逻辑：单文件模式 ===
        write_outputs = [
            item["code"]
            for item in context["intermediate_results"]
            if item["type"] == "write"
        ]

        if not write_outputs:
            step["output"] = {"text": "refine：未找到 write 步骤生成的代码。"}
            return

        code = write_outputs[-1]

        # 执行代码（使用 mock 环境）
        exec_result = None
        try:
            exec_result = run_python(FAKE_ENVIRONMENT + "\n\n" + code)
        except Exception as e:
            step["output"] = {"text": f"refine：代码执行失败：{e}"}
            return

        exec_summary = (
            f"stdout:\n{exec_result['stdout']}\n\n"
            f"stderr:\n{exec_result['stderr']}\n\n"
            f"error:\n{exec_result['error']}"
        )

        # 选择 API 调用函数
        api_func = context.get("_custom_api_func", call_local_llm)

        # 调用 LLM 优化代码
        optimized_text = ""
        llm_success = False

        try:
            prompt = optimize_prompt(code, exec_summary)

            if task_id:
                stream_chunk(task_id, "开始优化代码...\n", phase="refine", channel="reasoning")
                optimized_text = api_func(prompt)
                stream_chunk(task_id, optimized_text, phase="refine", channel="content")
            else:
                optimized_text = api_func(prompt)

            if not optimized_text:
                raise ValueError("LLM 返回空字符串")

            llm_success = True

        except Exception as e:
            err = f"# LLM 调用失败: {e}"
            optimized_text = err
            if task_id:
                stream_chunk(task_id, err, phase="refine", channel="reasoning")

        optimized_code = extract_code(optimized_text)

        # 写入输出
        step["output"] = {
            "text": optimized_text,
            "optimized_code": optimized_code,
            "exec_summary": exec_summary,
            "llm_success": llm_success
        }

        # 写入上下文
        context["intermediate_results"].append({
            "type": "refine",
            "original_code": code,
            "optimized_code": optimized_code,
            "exec_summary": exec_summary
        })

        # 写入事件流
        events.append(create_event("refine_output", {
            "original_code": code,
            "optimized_code": optimized_code,
            "exec_summary": exec_summary
        }))

        # ===== 流式输出结束 =====
        if task_id:
            try:
                stream_end(task_id)
            except Exception as e:
                print(f"[WARN] stream_end 失败: {e}")
        
        return

    # === v3.2 新逻辑：多文件模式 ===
    
    # 3) 构建虚拟项目（只包含 Python 文件）
    virtual_project = ""
    for fo in valid_file_ops:
        if fo.get("path", "").endswith(".py"):
            virtual_project += f"# FILE: {fo['path']}\n{fo.get('content', '')}\n\n"

    # 4) 执行整个项目（合并所有 Python 文件）
    exec_result = None
    try:
        exec_result = run_python(FAKE_ENVIRONMENT + "\n\n" + virtual_project)
    except Exception as e:
        step["output"] = {"text": f"refine：代码执行失败：{e}"}
        return

    exec_summary = (
        f"stdout:\n{exec_result['stdout']}\n\n"
        f"stderr:\n{exec_result['stderr']}\n\n"
        f"error:\n{exec_result['error']}"
    )

    # 5) 选择 API 调用函数
    api_func = context.get("_custom_api_func", call_local_llm)

    # 6) 调用 LLM 优化代码（⭐ 要求输出 # FILE: 协议格式）
    optimized_text = ""
    llm_success = False

    try:
        prompt = f"""请优化以下 Python 项目代码，保持多文件结构不变：

【当前项目】：
{virtual_project}

【执行结果】：
{exec_summary}

要求：
1. 必须使用 "# FILE:" 协议格式输出优化后的代码
2. 保持原有的文件数量和路径
3. 只优化代码内容，不改变文件结构
4. 不要输出任何解释性文字

现在开始优化：
"""

        if task_id:
            stream_chunk(task_id, "开始优化多文件项目...\n", phase="refine", channel="reasoning")
            optimized_text = api_func(prompt)
            stream_chunk(task_id, optimized_text, phase="refine", channel="content")
        else:
            optimized_text = api_func(prompt)

        if not optimized_text:
            raise ValueError("LLM 返回空字符串")

        llm_success = True

    except Exception as e:
        err = f"# LLM 调用失败: {e}"
        optimized_text = err
        if task_id:
            stream_chunk(task_id, err, phase="refine", channel="reasoning")

    # 7) ⭐ v3.2：解析模型输出的新 FileOps
    refined_file_ops = []
    try:
        if HAS_FILE_OPS:
            refined_file_ops = parse_fileops_v3(optimized_text)
        
        # ⭐ 方向 A：如果模型没有生成新的 file_ops，则保留原始 file_ops
        if refined_file_ops:
            # ⭐ 更新 final_file_ops（唯一真相源）
            context["final_file_ops"] = refined_file_ops
            context["file_ops"] = refined_file_ops
            print(f"✅ refine_step 更新 {len(refined_file_ops)} 个 FileOp")
        else:
            # 保持原有 file_ops 不变
            print("[INFO] refine_step: 模型未生成新 FileOps，保留原有结构")
            
    except Exception as e:
        print(f"[ERROR] refine_step 解析 FileOps 失败: {e}")
        import traceback
        traceback.print_exc()

    # 8) 写入输出
    step["output"] = {
        "text": optimized_text,
        "file_ops": context.get("final_file_ops", []),
        "exec_summary": exec_summary,
        "llm_success": llm_success
    }

    # 9) 写入上下文
    context["intermediate_results"].append({
        "type": "refine",
        "optimized_text": optimized_text,
        "exec_summary": exec_summary,
        "file_ops": context.get("final_file_ops", [])
    })

    # 10) 写入事件流
    events.append(create_event("refine_output", {
        "text": optimized_text,
        "file_ops": context.get("final_file_ops", []),
        "exec_summary": exec_summary
    }))

    # ===== 流式输出结束 =====
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
