# -*- coding: utf-8 -*-
# step_executor/refine_step.py — AlphaPilot OS v3.0
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - 所有代码执行、错误分析、优化都必须在 Worker 内完成
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - refine_step 必须输出 FileOps（唯一合法的文件操作方式）
#    - 必须支持多文件协议 v3.0
#
# 本模块负责：
# 1. 执行 write_step 生成的代码（多文件）
# 2. 根据执行结果优化整个项目
# 3. 输出新的 FileOps（覆盖旧文件）
# ⭐ 4. 支持流式输出（实时展示优化过程）
# ⭐ 5. 支持人格配置（从 context.meta 读取）
# ---------------------------------------------------------

from ..doubao_api import call_doubao, call_doubao_stream
from .prompts import optimize_prompt
from ....code_executor import run_python_project
from ....worker_config import create_event, stream_chunk, stream_start, stream_end
from ....file_ops import parse_fileops_v3


def run_refine_step(step, context, events, task_id=None):
    """
    refine 步骤（官方 + 智能增强版 + 流式输出 + 人格配置）
    ---------------------------------------------------------
    输入：
        - write_step 的多文件协议文本
    输出：
        - 优化后的多文件协议
        - 新的 FileOps（覆盖旧文件）
    
    ⭐ 流式输出支持：
        - 通过 task_id 发送 stream_chunk 事件
        - 实时展示 AI 优化过程 (channel=reasoning)
    
    ⭐ 人格配置支持：
        - 从 context.meta 读取 persona 类型
        - 动态注入 System Prompt
    """

    # ===== 第0层：启动流式输出 =====
    if task_id:
        try:
            stream_start(task_id, "🔧 正在优化代码...", phase="refine")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # ===== 第0.5层：⭐ 获取人格配置（豆包独立实现）=====
    persona_config = None
    try:
        meta = context.get("meta", {})
        persona_type = meta.get("persona", "engineer")
        
        from ..personas import get_persona_config
        persona_config = get_persona_config(persona_type)
        
        print(f"🎨 refine_step 使用人格: {persona_config['name']}")
    except Exception as e:
        print(f"[WARN] 获取人格配置失败: {e}")
        persona_config = None

    # =========================================================
    # ① 获取 write_step 的多文件协议文本
    # =========================================================
    write_outputs = [
        item["text"]
        for item in context["intermediate_results"]
        if item["type"] == "write"
    ]

    if not write_outputs:
        msg = "refine：未找到 write 步骤生成的代码或文件。"
        if task_id:
            stream_chunk(task_id, msg, phase="refine", channel="reasoning")
        step["output"] = {"text": msg}
        
        if task_id:
            try:
                stream_end(task_id)
            except Exception as e:
                print(f"[WARN] stream_end 失败: {e}")
        return

    all_code_context = write_outputs[-1]

    # =========================================================
    # ② 执行整个项目（多文件执行）
    # =========================================================
    exec_result = None
    exec_summary = ""
    
    try:
        exec_result = run_python_project(all_code_context)
        exec_summary = (
            f"stdout:\n{exec_result['stdout']}\n\n"
            f"stderr:\n{exec_result['stderr']}\n\n"
            f"error:\n{exec_result['error']}"
        )
    except Exception as e:
        exec_summary = f"refine：代码执行异常：{e}"
        
        if task_id:
            stream_chunk(task_id, exec_summary, phase="refine", channel="reasoning")

    # =========================================================
    # ③ 调用 LLM 优化整个项目（多文件优化 + 流式输出）
    # =========================================================
    optimized_text = ""
    llm_success = False
    
    try:
        # ⭐ 构建完整 prompt（含人格配置）
        if persona_config:
            system_prompt = persona_config.get("system_prompt", "")
            full_prompt = f"{system_prompt}\n\n---\n\n用户请求:\n{optimize_prompt(all_code_context, exec_summary)}"
        else:
            full_prompt = optimize_prompt(all_code_context, exec_summary)

        # ⭐ 使用流式调用
        if task_id:
            for chunk in call_doubao_stream(full_prompt):
                optimized_text += chunk
                stream_chunk(task_id, chunk, phase="refine", channel="content")
        else:
            # 非流式模式（向后兼容）
            optimized_text = call_doubao(full_prompt)

        llm_success = True

    except Exception as e:
        error_msg = f"refine：LLM 调用失败：{e}"
        optimized_text = error_msg
        
        if task_id:
            stream_chunk(task_id, error_msg, phase="refine", channel="reasoning")

    # =========================================================
    # ④ 解析优化后的多文件协议 → FileOps
    # =========================================================
    optimized_file_ops = []
    try:
        optimized_file_ops = parse_fileops_v3(optimized_text)
        print(f"✅ refine_step 生成 {len(optimized_file_ops)} 个 FileOp")
        
        # ⭐ 写入 context（使用 final_file_ops 作为唯一真相源）
        if "final_file_ops" not in context:
            context["final_file_ops"] = []
        
        # 追加而非覆盖
        context["final_file_ops"].extend(optimized_file_ops)
        
        # 向后兼容：仍然保留 file_ops 字段
        context["file_ops"] = context["final_file_ops"]
        
    except Exception as e:
        print(f"[ERROR] 解析 FileOps 失败: {e}")

    # =========================================================
    # ⑤ 写入输出
    # =========================================================
    step["output"] = {
        "text": optimized_text,
        "file_ops": optimized_file_ops,
        "exec_summary": exec_summary,
        "llm_success": llm_success
    }

    # =========================================================
    # ⑥ 写入上下文（供后续步骤使用）
    # =========================================================
    context["intermediate_results"].append({
        "type": "refine",
        "text": optimized_text,
        "file_ops": optimized_file_ops,
        "exec_summary": exec_summary,
        "llm_success": llm_success
    })

    # =========================================================
    # ⑦ 写入事件流（供 VSCode 实时展示）
    # =========================================================
    events.append(create_event("refine_output", {
        "text": optimized_text,
        "file_ops": optimized_file_ops,
        "exec_summary": exec_summary
    }))
    
    # ⭐ 结束流式输出
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
