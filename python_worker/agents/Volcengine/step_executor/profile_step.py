# -*- coding: utf-8 -*-
# step_executor/profile_step.py — AlphaPilot OS v3.0
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - 所有性能分析必须在 Worker 内完成
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - profile_step 可以输出 FileOps（例如 docs/performance.md）
#    - 必须支持多文件协议 v3.0
#
# 本模块负责：
# 1. 执行整个项目（多文件）
# 2. 分析性能瓶颈（LLM + 真实执行）
# 3. 输出性能报告（可选：写入 docs/performance.md）
# ⭐ 4. 支持流式输出（实时展示性能分析过程）
# ⭐ 5. 支持人格配置（从 context.meta 读取）
# ---------------------------------------------------------

from ..doubao_api import call_doubao, call_doubao_stream
from .prompts import profile_prompt
from ....code_executor import run_python_project
from ....worker_config import create_event, stream_chunk, stream_start, stream_end
from ....file_ops import parse_fileops_v3


def run_profile_step(step, context, events, task_id=None):
    """
    profile 步骤（官方 + 智能增强版 + 流式输出 + 人格配置）
    ---------------------------------------------------------
    输入：
        - write_step 的多文件协议文本
    输出：
        - 性能分析报告
        - 可选：FileOps（写入 docs/performance.md）
    
    ⭐ 流式输出支持：
        - 通过 task_id 发送 stream_chunk 事件
        - 实时展示 AI 性能分析过程 (channel=content)
    
    ⭐ 人格配置支持：
        - 从 context.meta 读取 persona 类型
        - 动态注入 System Prompt
    """

    # ===== 第0层：启动流式输出 =====
    if task_id:
        try:
            stream_start(task_id, "📊 正在分析性能...", phase="profile")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # ===== 第0.5层：⭐ 获取人格配置（豆包独立实现）=====
    persona_config = None
    try:
        meta = context.get("meta", {})
        persona_type = meta.get("persona", "engineer")
        
        from ..personas import get_persona_config
        persona_config = get_persona_config(persona_type)
        
        print(f"🎨 profile_step 使用人格: {persona_config['name']}")
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
        msg = "profile：未找到 write 步骤生成的代码或文件。"
        if task_id:
            stream_chunk(task_id, msg, phase="profile", channel="reasoning")
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
    exec_result = run_python_project(all_code_context)

    exec_summary = (
        f"stdout:\n{exec_result['stdout']}\n\n"
        f"stderr:\n{exec_result['stderr']}\n\n"
        f"error:\n{exec_result['error']}"
    )

    # =========================================================
    # ③ 调用 LLM 进行性能分析（多文件分析 + 流式输出）
    # =========================================================
    analysis_text = ""
    llm_success = False
    
    try:
        # ⭐ 构建完整 prompt（含人格配置）
        if persona_config:
            system_prompt = persona_config.get("system_prompt", "")
            full_prompt = f"{system_prompt}\n\n---\n\n用户请求:\n{profile_prompt(all_code_context)}"
        else:
            full_prompt = profile_prompt(all_code_context)

        # ⭐ 使用流式调用
        if task_id:
            for chunk in call_doubao_stream(full_prompt):
                analysis_text += chunk
                stream_chunk(task_id, chunk, phase="profile", channel="content")
        else:
            # 非流式模式（向后兼容）
            analysis_text = call_doubao(full_prompt)

        llm_success = True

    except Exception as e:
        error_msg = f"profile：LLM 调用失败：{e}"
        analysis_text = error_msg
        
        if task_id:
            stream_chunk(task_id, error_msg, phase="profile", channel="reasoning")

    # =========================================================
    # ④ 生成性能报告（可选：写入 docs/performance.md）
    # =========================================================
    performance_doc = f"""
# 项目性能分析报告

## 执行结果
{exec_summary}

## LLM 性能分析
{analysis_text}
"""

    # 包装成 FileOps（可选）
    performance_protocol = f"# DOC: docs/performance.md\n{performance_doc}"
    performance_file_ops = []
    
    try:
        performance_file_ops = parse_fileops_v3(performance_protocol)
        print(f"✅ profile_step 生成 {len(performance_file_ops)} 个 FileOp")
        
        # ⭐ 写入 context（使用 final_file_ops 作为唯一真相源）
        if "final_file_ops" not in context:
            context["final_file_ops"] = []
        
        # 追加而非覆盖
        context["final_file_ops"].extend(performance_file_ops)
        
        # 向后兼容：仍然保留 file_ops 字段
        context["file_ops"] = context["final_file_ops"]
        
    except Exception as e:
        print(f"[ERROR] 解析 FileOps 失败: {e}")

    # =========================================================
    # ⑤ 写入输出
    # =========================================================
    step["output"] = {
        "text": performance_doc,
        "file_ops": performance_file_ops,
        "exec_summary": exec_summary,
        "llm_success": llm_success
    }

    # =========================================================
    # ⑥ 写入上下文（供 refine_step 使用）
    # =========================================================
    context["intermediate_results"].append({
        "type": "profile",
        "text": performance_doc,
        "file_ops": performance_file_ops,
        "exec_summary": exec_summary,
        "llm_success": llm_success
    })

    # =========================================================
    # ⑦ 写入事件流（供 VSCode 实时展示）
    # =========================================================
    events.append(create_event("profile_output", {
        "text": performance_doc,
        "file_ops": performance_file_ops,
        "exec_summary": exec_summary
    }))
    
    # ⭐ 结束流式输出
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
